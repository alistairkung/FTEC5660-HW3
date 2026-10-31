"""Same-proposition gates and arithmetic; no materiality or investment verdicts."""
from decimal import Decimal, ROUND_HALF_EVEN

from .records import ClaimEvidenceMatch, EvidenceFact, FinancialSnapshot, ManagementClaim, PERIODS

MEASUREMENT_DEFINITIONS = {
    'revenue': 'sales_revenue', 'cost_of_sales': 'cost_of_sales', 'selling_admin': 'selling_admin',
    'research_development': 'research_development', 'operating_costs': 'cogs+sga+rd',
    'operating_profit': 'revenue-cogs-sga-rd', 'operating_margin_pct': '(revenue-cogs-sga-rd)/revenue',
    'return_rate': 'units_returned/units_shipped',
}


def evidence_facts(financial: FinancialSnapshot) -> tuple[EvidenceFact, ...]:
    company = financial.source.company_id
    facts = [EvidenceFact(metric.evidence_id, company, 'company', metric.metric, metric.period,
             metric.evidence_id.rsplit(':', 1)[-1], metric.value, metric.unit, metric.source_id,
             metric.comparison_period, metric.comparison_value, metric.absolute_change,
             metric.percentage_change, measurement_definition=MEASUREMENT_DEFINITIONS[metric.metric])
             for metric in financial.metrics]
    returns = {row.period: row for row in financial.returns}
    for period in PERIODS:
        if period not in returns:
            continue
        year, quarter = int(period[:4]), int(period[-1])
        previous = f'{year}Q{quarter - 1}' if quarter > 1 else f'{year - 1}Q4'
        row = returns[period]
        for basis, comparator in (('level', None), ('qoq', previous), ('yoy', f'{year - 1}Q{quarter}')):
            old = returns.get(comparator).rate_pct if comparator in returns else None
            delta = row.rate_pct - old if row.rate_pct is not None and old is not None else None
            change = delta / abs(old) * 100 if delta is not None and old else None
            facts.append(EvidenceFact(f'{period}:return_rate:{basis}', company, 'company',
                'return_rate', period, basis, row.rate_pct, 'percent', row.source_id,
                comparator, old, delta, change, row.units_shipped, MEASUREMENT_DEFINITIONS['return_rate']))
    return tuple(facts)


def match_claim(claim: ManagementClaim, fact: EvidenceFact | None) -> ClaimEvidenceMatch:
    """Unknown alignment cannot be upgraded to a factual contradiction."""
    def result(compatibility, relation, reason):
        return ClaimEvidenceMatch(claim.evidence_id, fact.evidence_id if fact else None,
                                  compatibility, relation, reason)

    proposition = claim.proposition
    if fact is None:
        return result('UNKNOWN', 'UNMATCHED', 'no_matching_fact')
    if proposition is None:
        return result('UNKNOWN', 'INCONCLUSIVE', 'unknown_proposition')
    for name, asserted, observed in (
        ('company', claim.company_id, fact.company_id),
        ('subject', proposition.subject, fact.subject),
        ('metric', proposition.metric, fact.metric),
        ('period', proposition.period, fact.period),
    ):
        if asserted in (None, '', 'unknown'):
            return result('UNKNOWN', 'INCONCLUSIVE', f'unknown_{name}')
        if asserted != observed:
            return result('INCOMPATIBLE', 'UNMATCHED', f'incompatible_{name}')
    if proposition.measurement_definition is None or fact.measurement_definition is None:
        return result('UNKNOWN', 'INCONCLUSIVE', 'unknown_measurement_definition')
    if proposition.measurement_definition != fact.measurement_definition:
        return result('INCOMPATIBLE', 'UNMATCHED', 'incompatible_measurement_definition')
    if proposition.basis is None:
        return result('UNKNOWN', 'INCONCLUSIVE', 'unknown_comparison_basis')
    if proposition.basis != fact.basis or proposition.comparator_period != fact.comparator_period:
        return result('INCOMPATIBLE', 'UNMATCHED', 'incompatible_comparator')
    if proposition.certainty != 'asserted':
        return result('UNKNOWN', 'INCONCLUSIVE', 'qualified_or_unknown_assertion')
    if proposition.assertion_type not in ('level', 'change', 'directional'):
        return result('UNKNOWN', 'INCONCLUSIVE', 'unsupported_assertion_type')
    if proposition.value is None:
        if proposition.unit is None:
            return result('UNKNOWN', 'INCONCLUSIVE', 'unknown_unit')
        if proposition.unit != fact.unit:
            return result('INCOMPATIBLE', 'UNMATCHED', 'incompatible_unit')
        if proposition.direction in ('low', 'high', 'stable'):
            return result('COMPATIBLE', 'INCONCLUSIVE', 'qualitative_criterion_unknown')
        if proposition.direction in ('increased', 'decreased'):
            if proposition.assertion_type not in ('change', 'directional') or fact.absolute_change is None:
                return result('UNKNOWN', 'INCONCLUSIVE', 'missing_directional_comparator')
            supported = {'increased': fact.absolute_change > 0, 'decreased': fact.absolute_change < 0}[proposition.direction]
            return result('COMPATIBLE', 'SUPPORTED' if supported else 'CONTRADICTED', 'measured_direction')
        return result('UNKNOWN', 'INCONCLUSIVE', 'unquantified_event_or_claim')
    if proposition.direction in ('low', 'high'):
        return result('COMPATIBLE', 'INCONCLUSIVE', 'qualitative_criterion_unknown')
    asserted_value = proposition.value
    if proposition.assertion_type in ('change', 'directional'):
        if proposition.direction == 'decreased':
            asserted_value = -abs(asserted_value)
        elif ((proposition.direction == 'increased' and asserted_value < 0)
              or (proposition.direction == 'stable' and asserted_value != 0)):
            return result('UNKNOWN', 'INCONCLUSIVE', 'inconsistent_signed_change')
    value, unit = fact.value, fact.unit
    if proposition.assertion_type in ('change', 'directional'):
        if proposition.unit == 'percent':
            value, unit = fact.percentage_change, 'percent'
        else:
            value = fact.absolute_change
            if proposition.unit == 'percentage_points' and fact.unit == 'percent':
                unit = 'percentage_points'
    if proposition.unit in ('USD_thousands', 'USD_millions') and unit in ('USD_thousands', 'USD_millions'):
        if value is not None and proposition.unit != unit:
            value = value / Decimal(1000) if proposition.unit == 'USD_millions' else value * Decimal(1000)
    elif proposition.unit != unit:
        return result('INCOMPATIBLE', 'UNMATCHED', 'incompatible_unit')
    if value is None:
        return result('UNKNOWN', 'INCONCLUSIVE', 'undefined_measurement')
    # The copied decimal token defines reporting precision, not a fitted tolerance.
    displayed = value.quantize(Decimal(1).scaleb(asserted_value.as_tuple().exponent), rounding=ROUND_HALF_EVEN)
    return result('COMPATIBLE', 'SUPPORTED' if displayed == asserted_value else 'CONTRADICTED',
                  'numeric_at_quoted_precision')
