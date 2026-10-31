"""Direct returns evidence uses independently worked quarterly counts."""
import unittest

from fisher_agent.point14.financial_evidence_extractor import FinancialEvidenceExtractor
import test_point14_financial as financial_fixture


class ReturnsTests(unittest.IsolatedAsyncioTestCase):
    async def test_quarterly_rate_is_ratio_of_sums_with_counts_period_and_source(self):
        snapshot = await FinancialEvidenceExtractor().extract(
            'synthetic', financial_fixture.FinancialTests().synthetic_database())
        fact = next(row for row in snapshot.returns if row.period == '2025Q3')
        self.assertEqual(fact.units_shipped, 1000)
        self.assertEqual(fact.units_returned, 26)
        self.assertEqual(str(fact.rate_pct), '2.600')
        self.assertEqual(fact.source_id, snapshot.source.evidence_id)
        self.assertEqual(len(snapshot.returns), 10)

    async def test_zero_denominator_remains_explicit_unknown_not_zero_rate(self):
        tool = financial_fixture.FinancialTests().synthetic_database(return_mutation=
            "UPDATE returns SET units_shipped=0, units_returned=0 WHERE month BETWEEN '2025-07' AND '2025-09'")
        snapshot = await FinancialEvidenceExtractor().extract('synthetic', tool)
        row = next(row for row in snapshot.returns if row.period == '2025Q3')
        self.assertIsNone(row.rate_pct)
        self.assertEqual(row.status, 'zero_denominator')

    async def test_missing_duplicate_and_invalid_counts_are_rejected(self):
        mutations = [
            "DELETE FROM returns WHERE month='2025-07'",
            "INSERT INTO returns VALUES ('2025-07', 100, 1)",
            "UPDATE returns SET units_returned='bad' WHERE month='2025-07'",
            "UPDATE returns SET units_returned=-1 WHERE month='2025-07'",
            "UPDATE returns SET units_returned=1.5 WHERE month='2025-07'",
            "UPDATE returns SET month='2025-07x' WHERE month='2025-07'",
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                await FinancialEvidenceExtractor().extract('synthetic',
                    financial_fixture.FinancialTests().synthetic_database(return_mutation=mutation))
