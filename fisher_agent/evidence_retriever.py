"""Point 5 SQL access and decoding, exclusively through an injected tool."""

from decimal import Decimal, InvalidOperation
from hashlib import sha256

from fisher_agent.contracts import AnnualMargin, SQLEvidence, SQLTool
from fisher_agent.point_rules import operating_margin_pct


ANNUAL_COLUMNS = ('year', 'revenue', 'operating_costs', 'order_count',
                  'invalid_orders', 'cost_rows', 'cost_months', 'invalid_costs')
MEDIAN_COLUMNS = ('industry', 'operating_margin_pct')
MEDIAN_QUERY = '''SELECT c.industry, m.operating_margin_pct
FROM company AS c
JOIN industry_medians AS m ON m.industry = c.industry'''


class EvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EvidenceRetriever:
    def __init__(self, company_id: str, sql_query: SQLTool) -> None:
        self.company_id = company_id
        self.sql_query = sql_query
        self.evidence: list[SQLEvidence] = []

    def query(self, query: str, columns: tuple[str, ...]) -> SQLEvidence:
        evidence_id = f'{self.company_id}:sql:{sha256(query.encode()).hexdigest()[:16]}'
        try:
            raw = self.sql_query.invoke({'query': query})
        except Exception as error:
            self.evidence.append(SQLEvidence(evidence_id, self.company_id, query, None))
            raise EvidenceError('sql_error', f'SQL tool raised {type(error).__name__}') from error
        lines = raw.strip().splitlines() if isinstance(raw, str) else []
        header = tuple(cell.strip() for cell in lines[0].split('|')) if lines else ()
        rows = tuple(tuple(cell.strip() for cell in line.split('|')) for line in lines[1:])
        item = SQLEvidence(evidence_id,
                           self.company_id, query, raw if isinstance(raw, str) else None, header, rows)
        self.evidence.append(item)
        if lines and lines[0].startswith('SQL error:'):
            raise EvidenceError('sql_error', lines[0])
        if any(line.startswith('... more rows not shown') for line in lines):
            raise EvidenceError('truncated_result', 'SQL result was truncated')
        if lines and (len(lines) == 1 or lines[1:] == ['(no rows)']) and header == columns:
            raise EvidenceError('missing_data', 'SQL returned no rows')
        if header != columns or any(len(row) != len(columns) for row in rows):
            raise EvidenceError('invalid_result', 'Unexpected SQL columns or row shape')
        return item

    def annual_margins(self, years: tuple[int, ...]) -> tuple[AnnualMargin, ...]:
        first, last = min(years), max(years)
        # Aggregate each table before joining: a raw orders/costs join multiplies totals.
        query = f'''WITH revenue AS (
    SELECT substr(order_date, 1, 4) AS year, SUM(amount) AS revenue,
           COUNT(*) AS order_count,
           SUM(CASE WHEN typeof(amount) IN ('integer', 'real') THEN 0 ELSE 1 END) AS invalid_orders
    FROM orders WHERE order_date >= '{first}-01-01' AND order_date < '{last + 1}-01-01'
    GROUP BY substr(order_date, 1, 4)
), costs AS (
    SELECT substr(month, 1, 4) AS year,
           SUM(cost_of_sales + selling_admin + research_development) AS operating_costs,
           COUNT(*) AS cost_rows, COUNT(DISTINCT month) AS cost_months,
           SUM(CASE WHEN typeof(cost_of_sales) IN ('integer', 'real')
                     AND typeof(selling_admin) IN ('integer', 'real')
                     AND typeof(research_development) IN ('integer', 'real')
                    THEN 0 ELSE 1 END) AS invalid_costs
    FROM monthly_costs WHERE month >= '{first}-01' AND month < '{last + 1}-01'
    GROUP BY substr(month, 1, 4)
)
SELECT r.year, r.revenue, c.operating_costs, r.order_count, r.invalid_orders,
       c.cost_rows, c.cost_months, c.invalid_costs
FROM revenue AS r LEFT JOIN costs AS c ON c.year = r.year ORDER BY r.year'''
        item = self.query(query, ANNUAL_COLUMNS)
        if tuple(row[0] for row in item.rows) != tuple(str(year) for year in years):
            raise EvidenceError('missing_data', 'Expected exactly one row for each requested year')
        margins = []
        for row in item.rows:
            revenue, costs = number(row[1]), number(row[2])
            orders, invalid_orders, cost_rows, months, invalid_costs = map(number, row[3:])
            if invalid_orders != 0 or invalid_costs != 0:
                raise EvidenceError('invalid_number', 'Source rows contain missing or nonnumeric amounts')
            if orders < 1 or orders != orders.to_integral_value() or cost_rows != 12 or months != 12:
                raise EvidenceError('missing_data', 'Need revenue and twelve unique monthly cost rows per year')
            try:
                margin = operating_margin_pct(revenue, costs)
            except ValueError as error:
                raise EvidenceError('invalid_number', str(error)) from error
            margins.append(AnnualMargin(int(row[0]), revenue, costs, margin, item.evidence_id))
        return tuple(margins)

    def industry_median(self) -> Decimal:
        item = self.query(MEDIAN_QUERY, MEDIAN_COLUMNS)
        if len(item.rows) != 1:
            raise EvidenceError('missing_data', 'Expected exactly one matching industry median')
        return number(item.rows[0][1])


def number(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise EvidenceError('invalid_number', f'Invalid SQL numeric value: {value!r}') from error
    if not parsed.is_finite():
        raise EvidenceError('invalid_number', 'SQL numeric value must be finite')
    return parsed
