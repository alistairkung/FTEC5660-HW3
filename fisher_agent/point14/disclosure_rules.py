"""Prepare event candidates and gate scoped disclosure conclusions in Python."""
from datetime import date
import re

from .records import (AdverseEvent, ClaimEvidenceMatch, CommunicationCoverage, DisclosureFinding,
                      EvidenceFact, PERIODS, Transcript, TransparencyDecision)


def prepare_events(facts: tuple[EvidenceFact, ...]) -> tuple[AdverseEvent, ...]:
    groups: dict[tuple[str, str], list[str]] = {}
    for fact in facts:
        if fact.absolute_change is None or fact.basis not in ('qoq', 'yoy'):
            continue
        increasing = fact.metric in ('return_rate', 'cost_of_sales', 'selling_admin',
                                     'research_development', 'operating_costs')
        decreasing = fact.metric in ('revenue', 'operating_profit', 'operating_margin_pct')
        if (increasing and fact.absolute_change > 0) or (decreasing and fact.absolute_change < 0):
            groups.setdefault((fact.period, fact.metric), []).append(fact.evidence_id)
    return tuple(AdverseEvent(f'event:{period}:{metric}', metric, period, tuple(ids))
                 for (period, metric), ids in sorted(groups.items()))


def communication_coverage(transcripts: tuple[Transcript, ...], *, measurements_complete: bool = True
                           ) -> CommunicationCoverage:
    gaps = []
    periods = tuple(doc.period for doc in transcripts)
    if len(periods) != len(set(periods)) or set(periods) != set(PERIODS):
        gaps.append('missing_or_duplicate_call')
    if len({doc.source.company_id for doc in transcripts}) != 1:
        gaps.append('mixed_company_sources')
    for doc in transcripts:
        if doc.name != f'earnings_call_{doc.period.lower()}.md':
            gaps.append('unexpected_document_scope')
        dated = re.search(r'^Date:\s*(\d{4}-\d{2}-\d{2})\s*$', doc.source.raw, re.MULTILINE)
        try:
            when = date.fromisoformat(dated.group(1)) if dated else None
        except ValueError:
            when = None
        if when is None:
            gaps.append('unknown_communication_date')
        elif (when.year, when.month) <= (int(doc.period[:4]), 3 * int(doc.period[-1])):
            gaps.append('communication_precedes_completed_quarter')
    if not measurements_complete:
        gaps.append('incomplete_measurement_scope')
    return CommunicationCoverage('four_supplied_earnings_calls', tuple(PERIODS), periods,
                                 not gaps, tuple(sorted(set(gaps))))


def aggregate_findings(matches: tuple[ClaimEvidenceMatch, ...], disclosures: tuple[DisclosureFinding, ...],
                       coverage: CommunicationCoverage) -> TransparencyDecision:
    reasons = list(coverage.gaps)
    if not coverage.complete:
        reasons.append('incomplete_scoped_coverage')
    if any(match.relation == 'CONTRADICTED' for match in matches):
        reasons.append('misstatement_policy_unresolved')
    if any(match.relation in ('INCONCLUSIVE', 'UNMATCHED') for match in matches):
        reasons.append('unresolved_proposition_matching')
    for finding in disclosures:
        if finding.materiality == 'UNKNOWN':
            reasons.append('unknown_materiality')
        if finding.materiality != 'IMMATERIAL':
            if finding.knowledge == 'UNKNOWN':
                reasons.append('unknown_management_knowledge')
                if finding.relation == 'NOT_FOUND':
                    reasons.append('omission_knowledge_policy_unresolved')
            if finding.relation == 'INCONCLUSIVE':
                reasons.append('unresolved_disclosure')
    if reasons:
        assessment = 'INSUFFICIENT_EVIDENCE'
    elif any(d.relation == 'NOT_FOUND' and d.materiality == 'MATERIAL'
             and d.knowledge == 'ESTABLISHED' for d in disclosures):
        assessment = 'EVASIVE'
    else:
        assessment = 'TRANSPARENT'
    return TransparencyDecision(assessment, tuple(sorted(set(reasons))), matches, disclosures)
