import unittest
from langchain_core.tools import tool

from fisher_agent.point14.financial_evidence_extractor import FinancialEvidenceExtractor


@tool
def financial_sql(query: str) -> str:
    """Return independently worked quarterly totals in USD thousands."""
    header = 'quarter | revenue | order_months | cost_of_sales | selling_admin | research_development | cost_months | valid_orders | total_orders | valid_costs | total_costs | units_shipped | units_returned | return_rows | return_months | valid_returns'
    rows = []
    revenues = [80, 100, 120, 160, 200, 180, 150, 100, 100, 90]
    for i, revenue in enumerate(revenues):
        quarter = f'{2024 + i // 4}Q{i % 4 + 1}'
        rows.append(f'{quarter} | {revenue} | 3 | 40 | 10 | 10 | 3 | 10 | 10 | 3 | 3 | 1000 | 26 | 3 | 3 | 3')
    return header + '\n' + '\n'.join(rows)


class FinancialTests(unittest.IsolatedAsyncioTestCase):
    async def test_quarterly_metrics_have_comparisons_units_and_provenance(self):
        snapshot = await FinancialEvidenceExtractor().extract('synthetic', financial_sql)
        revenue = next(m for m in snapshot.metrics if m.evidence_id == '2025Q3:revenue:qoq')
        self.assertEqual(revenue.value, 150)
        self.assertEqual(revenue.comparison_value, 180)
        self.assertEqual(revenue.comparison_period, '2025Q2')
        self.assertAlmostEqual(float(revenue.percentage_change), -16.6666667)
        yoy = next(m for m in snapshot.metrics if m.evidence_id == '2025Q3:revenue:yoy')
        self.assertEqual(yoy.comparison_value, 120)
        self.assertEqual(yoy.percentage_change, 25)
        profit = next(m for m in snapshot.metrics if m.evidence_id == '2025Q3:operating_profit:level')
        self.assertEqual(profit.value, 90)
        self.assertEqual(profit.unit, 'USD_thousands')
        margin = next(m for m in snapshot.metrics if m.evidence_id == '2025Q3:operating_margin_pct:level')
        self.assertEqual(margin.value, 60)
        self.assertEqual(margin.unit, 'percent')
        self.assertIn('SUM', snapshot.source.arguments['query'])
        self.assertEqual(snapshot.source.company_id, 'synthetic')

    async def test_rejects_incomplete_zero_nonfinite_failed_and_truncated_data(self):
        from unittest.mock import AsyncMock
        good = financial_sql.invoke({'query': ''})
        bad_responses = [
            'SQL error: no such table', '',
            good + '\n... more rows not shown (limit 50)',
            good.replace('2025Q3 | 150', '2025Q3 | 0'),
            good.replace('2025Q3 | 150', '2025Q3 | NaN'),
            good.replace('2025Q3 | 150', '2025Q3 | USD150'),
            '\n'.join(line for line in good.splitlines() if not line.startswith('2025Q2')),
            good.replace('2025Q3 | 150 | 3', '2025Q3 | 150 | 2'),
            good.replace('2025Q3 | 150', '2025Q2 | 150'),
            good.replace('| 40 | 10 | 10 | 3', '| 40 | 10 | 10 | 2'),
            good.replace('| 10 | 10 | 3', '| 9 | 10 | 3'),
        ]
        for response in bad_responses:
            with self.subTest(response=response[:60]):
                with self.assertRaises(ValueError):
                    await FinancialEvidenceExtractor().extract('x', AsyncMock(ainvoke=AsyncMock(return_value=response)))

    async def test_zero_profit_comparison_has_explicit_zero_denominator(self):
        from unittest.mock import AsyncMock
        raw = financial_sql.invoke({'query': ''}).replace('2025Q2 | 180', '2025Q2 | 60')
        snapshot = await FinancialEvidenceExtractor().extract('x', AsyncMock(ainvoke=AsyncMock(return_value=raw)))
        metric = next(m for m in snapshot.metrics if m.evidence_id == '2025Q3:operating_profit:qoq')
        self.assertEqual(metric.absolute_change, 90)
        self.assertIsNone(metric.percentage_change)
        self.assertEqual(metric.comparison_status, 'zero_denominator')

    def synthetic_database(self, *, duplicate_invalid_cost=False, return_mutation=None):
        import sqlite3
        from contextlib import closing
        from langchain_core.tools import tool

        @tool
        def synthetic_database(query: str) -> str:
            """Execute against a synthetic in-memory fixture, never company files."""
            with closing(sqlite3.connect(':memory:')) as db:
                db.executescript('CREATE TABLE orders(order_date TEXT, amount REAL); '
                                 'CREATE TABLE monthly_costs(month TEXT, cost_of_sales REAL, '
                                 'selling_admin REAL, research_development REAL); '
                                 'CREATE TABLE returns(month TEXT, units_shipped, units_returned);')
                for year in (2024, 2025, 2026):
                    for month in range(1, 13 if year < 2026 else 7):
                        # Two orders per month: quarterly revenue=600, costs=180.
                        db.executemany('INSERT INTO orders VALUES (?, ?)',
                                       [(f'{year}-{month:02}-01', 120), (f'{year}-{month:02}-15', 80)])
                        db.execute('INSERT INTO monthly_costs VALUES (?, 40, 10, 10)',
                                   (f'{year}-{month:02}',))
                        shipped, returned = ((100, 1), (200, 4), (700, 21))[(month - 1) % 3]
                        db.execute('INSERT INTO returns VALUES (?, ?, ?)',
                                   (f'{year}-{month:02}', shipped, returned))
                if duplicate_invalid_cost:
                    db.execute("INSERT INTO monthly_costs VALUES ('2025-07', 9999, NULL, 1000)")
                if return_mutation:
                    db.execute(return_mutation)
                cursor = db.execute(query)
                return '\n'.join([' | '.join(c[0] for c in cursor.description)] +
                                 [' | '.join(str(v) for v in row) for row in cursor.fetchall()])
        return synthetic_database

    async def test_sql_aggregates_real_synthetic_orders_without_join_multiplication(self):
        snapshot = await FinancialEvidenceExtractor().extract('synthetic', self.synthetic_database())
        metrics = {m.evidence_id:m for m in snapshot.metrics}
        self.assertEqual(metrics['2025Q3:revenue:level'].value, 600)
        self.assertEqual(metrics['2025Q3:operating_profit:level'].value, 420)
        self.assertEqual(metrics['2025Q3:operating_margin_pct:level'].value, 70)
        self.assertEqual(metrics['2026Q1:revenue:qoq'].comparison_period, '2025Q4')

    async def test_rejects_extra_invalid_cost_row_even_when_three_months_are_valid(self):
        # Previously accepted: costs became 10,119 and profit became -10,579.
        with self.assertRaises(ValueError):
            await FinancialEvidenceExtractor().extract(
                'synthetic', self.synthetic_database(duplicate_invalid_cost=True))
