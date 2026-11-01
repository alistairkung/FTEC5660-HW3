"""Single-table SQL evidence and exact integer pooled-baseline comparisons."""
from decimal import Decimal, InvalidOperation

from .records import EvidenceError, QuarterReturns, RateComparison

PERIODS = tuple(f'{2024+i//4}Q{i%4+1}' for i in range(2,10))
REPORTING_PERIODS = PERIODS[4:]
COLUMNS = ('quarter', 'row_count', 'month_count', 'valid_count', 'units_shipped', 'units_returned')
VALID_MONTH = """length(month)=7 AND month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
    AND substr(month,6,2) BETWEEN '01' AND '12'"""
VALID_COUNT = """typeof(units_shipped) IN ('integer','real')
    AND typeof(units_returned) IN ('integer','real')
    AND units_shipped >= 0 AND units_returned >= 0
    AND units_returned <= units_shipped
    AND units_shipped = CAST(units_shipped AS INTEGER)
    AND units_returned = CAST(units_returned AS INTEGER)"""
# Cast validated integral inputs before SUM, retaining exact integer totals through
# the lecturer tool (which rounds floating SQL outputs to two decimal places).
RETURNS_QUERY = f'''SELECT substr(month,1,4) || 'Q' ||
    CAST((CAST(substr(month,6,2) AS INTEGER)+2)/3 AS INTEGER) AS quarter,
    COUNT(*) AS row_count, COUNT(DISTINCT month) AS month_count,
    SUM(CASE WHEN {VALID_MONTH} AND {VALID_COUNT} THEN 1 ELSE 0 END) AS valid_count,
    CAST(SUM(CASE WHEN {VALID_COUNT} THEN CAST(units_shipped AS INTEGER) ELSE 0 END) AS TEXT) AS units_shipped,
    CAST(SUM(CASE WHEN {VALID_COUNT} THEN CAST(units_returned AS INTEGER) ELSE 0 END) AS TEXT) AS units_returned
FROM returns
WHERE (month >= '2024-07' AND month < '2026-07') OR month IS NULL OR NOT ({VALID_MONTH})
GROUP BY quarter ORDER BY quarter'''


def _integer(value: str) -> int:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise EvidenceError('invalid_returns_count') from error
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise EvidenceError('invalid_returns_count')
    return int(number)


def decode_quarters(raw: str, company_id: str, source_id: str) -> tuple[QuarterReturns, ...]:
    if not isinstance(raw, str) or raw.startswith('SQL error:'):
        raise EvidenceError('sql_error')
    lines = raw.strip().splitlines()
    if any(line.startswith('... more rows not shown') for line in lines):
        raise EvidenceError('truncated_returns')
    if not lines or tuple(c.strip() for c in lines[0].split('|')) != COLUMNS:
        raise EvidenceError('invalid_returns_result')
    rows = [tuple(c.strip() for c in line.split('|')) for line in lines[1:]]
    if any(len(row) != len(COLUMNS) for row in rows) or tuple(row[0] for row in rows) != PERIODS:
        raise EvidenceError('incomplete_returns_history')
    quarters = []
    for period, count, months, valid, shipped, returned in rows:
        if tuple(map(_integer, (count, months, valid))) != (3, 3, 3):
            raise EvidenceError('invalid_monthly_returns')
        shipped_count, returned_count = _integer(shipped), _integer(returned)
        if returned_count > shipped_count:
            raise EvidenceError('inconsistent_returns_count')
        quarters.append(QuarterReturns(period, shipped_count, returned_count, source_id, company_id))
    return tuple(quarters)


def compare_quarters(quarters: tuple[QuarterReturns, ...]) -> tuple[RateComparison, ...]:
    if tuple(q.period for q in quarters) != PERIODS:
        raise EvidenceError('incomplete_returns_history')
    if (len({q.company_id for q in quarters}) != 1 or not quarters[0].company_id
            or len({q.source_id for q in quarters}) != 1 or not quarters[0].source_id):
        raise EvidenceError('inconsistent_returns_provenance')
    if any(q.shipped <= 0 or q.returned < 0 for q in quarters):
        raise EvidenceError('undefined_returns_rate')
    comparisons = []
    for index in range(4, 8):
        current = quarters[index]
        history = quarters[index-4:index]
        shipped, returned = sum(q.shipped for q in history), sum(q.returned for q in history)
        # User-authorized edge: no returns now or in baseline is not an anomaly.
        anomalous = (current.returned > 0 and current.returned * shipped >= 2 * returned * current.shipped)
        ratio = (Decimal(current.returned * shipped) / Decimal(returned * current.shipped)
                 if returned else None)
        comparisons.append(RateComparison(current.period, current.shipped, current.returned,
            shipped, returned, anomalous, ratio, returned == 0, current.company_id,
            current.source_id, Decimal(current.returned)*100/Decimal(current.shipped),
            Decimal(returned)*100/Decimal(shipped)))
    return tuple(comparisons)
