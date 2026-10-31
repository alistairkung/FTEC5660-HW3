"""Deterministic financial extraction via the supplied company-scoped SQL tool."""
from decimal import Decimal, InvalidOperation
from typing import Any

from .records import EvidenceError, FinancialMetric, FinancialSnapshot, PERIODS, QuarterlyReturns, Source

# Ten quarters supply previous-quarter and previous-year comparators for all calls.
# Aggregate each table separately to avoid multiplying orders by monthly costs.
FINANCIAL_QUERY = """
WITH r AS (
 SELECT substr(order_date,1,4)||'Q'||((CAST(substr(order_date,6,2) AS INTEGER)+2)/3) AS quarter,
 SUM(amount) AS revenue, COUNT(DISTINCT substr(order_date,1,7)) AS order_months,
 COUNT(*) AS total_orders,
 SUM(CASE WHEN typeof(amount) IN ('integer','real') THEN 1 ELSE 0 END) AS valid_orders
 FROM orders WHERE order_date >= '2024-01-01' AND order_date < '2026-07-01'
 GROUP BY quarter
), c AS (
 SELECT substr(month,1,4)||'Q'||((CAST(substr(month,6,2) AS INTEGER)+2)/3) AS quarter,
 SUM(cost_of_sales) AS cost_of_sales, SUM(selling_admin) AS selling_admin,
 SUM(research_development) AS research_development, COUNT(DISTINCT month) AS cost_months,
 COUNT(*) AS total_costs,
 SUM(CASE WHEN typeof(cost_of_sales) IN ('integer','real')
 AND typeof(selling_admin) IN ('integer','real')
 AND typeof(research_development) IN ('integer','real') THEN 1 ELSE 0 END) AS valid_costs
 FROM monthly_costs WHERE month >= '2024-01' AND month < '2026-07'
 GROUP BY quarter
), t AS (
 SELECT substr(month,1,4)||'Q'||((CAST(substr(month,6,2) AS INTEGER)+2)/3) AS quarter,
 SUM(units_shipped) AS units_shipped, SUM(units_returned) AS units_returned,
 COUNT(*) AS return_rows, COUNT(DISTINCT month) AS return_months,
 SUM(CASE WHEN typeof(units_shipped) IN ('integer','real')
 AND typeof(units_returned) IN ('integer','real')
 AND units_shipped >= 0 AND units_returned >= 0
 AND length(month) = 7 AND month GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'
 AND CAST(substr(month,6,2) AS INTEGER) BETWEEN 1 AND 12
 AND units_shipped = CAST(units_shipped AS INTEGER)
 AND units_returned = CAST(units_returned AS INTEGER) THEN 1 ELSE 0 END) AS valid_returns
 FROM returns WHERE month >= '2024-01' AND month < '2026-07'
 GROUP BY quarter
)
SELECT r.quarter, revenue, order_months, cost_of_sales, selling_admin,
 research_development, cost_months, valid_orders, total_orders, valid_costs, total_costs,
 units_shipped, units_returned, return_rows, return_months, valid_returns
FROM r LEFT JOIN c ON r.quarter=c.quarter LEFT JOIN t ON r.quarter=t.quarter ORDER BY r.quarter
""".strip()
COLUMNS = ('quarter', 'revenue', 'order_months', 'cost_of_sales', 'selling_admin',
           'research_development', 'cost_months', 'valid_orders', 'total_orders', 'valid_costs', 'total_costs',
           'units_shipped', 'units_returned', 'return_rows', 'return_months', 'valid_returns')


def decode_sql(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, str) or not raw.strip():
        raise EvidenceError('Missing SQL response')
    lines = raw.strip().splitlines()
    if tuple(p.strip() for p in lines[0].split('|')) != COLUMNS:
        raise EvidenceError('SQL failed or returned unexpected columns')
    if len(lines) < 2 or len(lines) > 51 or any(
        'more rows not shown' in line or '(no rows)' in line for line in lines[1:]
    ):
        raise EvidenceError('Empty or truncated SQL response')
    rows = []
    for line in lines[1:]:
        values = [part.strip() for part in line.split('|')]
        if len(values) != len(COLUMNS):
            raise EvidenceError('Malformed SQL row')
        rows.append(dict(zip(COLUMNS, values)))
    return rows


def number(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise EvidenceError('Invalid financial number') from exc
    if not value.is_finite():
        raise EvidenceError('Non-finite financial number')
    return value


class FinancialEvidenceExtractor:
    async def extract(self, company_id: str, sql_query: Any, *, config: dict | None = None
                      ) -> FinancialSnapshot:
        raw = await sql_query.ainvoke({'query': FINANCIAL_QUERY}, config=config)
        rows = decode_sql(raw)
        source = Source('point14:financial_sql', company_id, 'sql_query',
                        {'query': FINANCIAL_QUERY}, raw)
        quarterly: dict[str, dict[str, Decimal]] = {}
        returns = []
        expected = {f'{year}Q{quarter}' for year in (2024, 2025, 2026)
                    for quarter in range(1, 5) if year != 2026 or quarter <= 2}
        for row in rows:
            period = row['quarter']
            if period not in expected or period in quarterly:
                raise EvidenceError('Unexpected or duplicate financial period')
            values = {key: number(value) for key, value in row.items() if key != 'quarter'}
            if any(values[key] != 3 for key in ('order_months', 'cost_months', 'valid_costs', 'total_costs')):
                raise EvidenceError('Incomplete quarter or invalid monthly costs')
            if any(values[key] != 3 for key in ('return_rows', 'return_months', 'valid_returns')):
                raise EvidenceError('Incomplete, duplicated or invalid monthly returns')
            shipped, returned = values['units_shipped'], values['units_returned']
            if shipped == 0 and returned != 0:
                raise EvidenceError('Returns without shipments cannot define a return rate')
            returns.append(QuarterlyReturns(period, shipped, returned,
                returned / shipped * 100 if shipped else None, source.evidence_id,
                'complete' if shipped else 'zero_denominator'))
            if values['total_orders'] <= 0 or values['valid_orders'] != values['total_orders']:
                raise EvidenceError('Missing or invalid orders')
            revenue = values['revenue']
            if revenue <= 0:
                raise EvidenceError('Non-positive revenue prevents reliable margin calculation')
            expenses = sum(values[key] for key in
                           ('cost_of_sales', 'selling_admin', 'research_development'))
            quarterly[period] = {
                'revenue': revenue, 'cost_of_sales': values['cost_of_sales'],
                'selling_admin': values['selling_admin'],
                'research_development': values['research_development'],
                'operating_costs': expenses, 'operating_profit': revenue - expenses,
                'operating_margin_pct': (revenue - expenses) / revenue * 100,
            }
        if set(quarterly) != expected:
            raise EvidenceError('Missing quarterly comparison data')
        metrics = []
        for period in PERIODS:
            year, quarter = int(period[:4]), int(period[-1])
            previous = f'{year}Q{quarter-1}' if quarter > 1 else f'{year-1}Q4'
            comparisons = (('level', None), ('qoq', previous), ('yoy', f'{year-1}Q{quarter}'))
            for metric, value in quarterly[period].items():
                for comparison, comparison_period in comparisons:
                    old = quarterly[comparison_period][metric] if comparison_period else None
                    delta = value - old if old is not None else None
                    percentage = (delta / abs(old) * 100) if old else None
                    status = 'level' if old is None else 'zero_denominator' if old == 0 else 'available'
                    metrics.append(FinancialMetric(
                        f'{period}:{metric}:{comparison}', period, metric, value,
                        'percent' if metric == 'operating_margin_pct' else 'USD_thousands',
                        source.evidence_id, comparison_period, old, delta, percentage, status))
        return FinancialSnapshot(tuple(metrics), source, tuple(returns))
