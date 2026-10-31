"""Scoped absence, knowledge and truth findings remain independent."""
from dataclasses import replace
from decimal import Decimal
import unittest

from fisher_agent.point14.disclosure_rules import aggregate_findings, communication_coverage, prepare_events
from fisher_agent.point14.records import (ClaimEvidenceMatch, CommunicationCoverage, DisclosureFinding,
    EvidenceFact, PERIODS, Source, Transcript)


def coverage():
    return CommunicationCoverage('four_supplied_earnings_calls', tuple(PERIODS), tuple(PERIODS), True, ())


class DisclosureTests(unittest.TestCase):
    def test_event_candidates_are_prepared_before_matching_or_claim_search(self):
        fact = EvidenceFact('q1:returns', 'x', 'company', 'return_rate', '2026Q1', 'qoq',
                            Decimal('5.09'), 'percent', 'sql', '2025Q4', Decimal('1.7'), Decimal('3.39'))
        events = prepare_events((fact,))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].fact_ids, ('q1:returns',))
        self.assertEqual(events[0].status, 'candidate')

    def test_not_found_with_unknown_materiality_or_knowledge_is_not_concealment(self):
        finding = DisclosureFinding('event:1', 'NOT_FOUND', (), 'UNKNOWN', 'UNKNOWN')
        decision = aggregate_findings((), (finding,), coverage())
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')
        self.assertIn('unknown_materiality', decision.reasons)
        self.assertIn('unknown_management_knowledge', decision.reasons)

    def test_numeric_contradiction_does_not_cancel_candid_different_event(self):
        mismatch = ClaimEvidenceMatch('q1:revenue-claim', 'q1:revenue', 'COMPATIBLE',
                                      'CONTRADICTED', 'numeric_at_quoted_precision')
        candid = DisclosureFinding('q3:returns', 'ACKNOWLEDGED', ('q3:admission',), 'MATERIAL', 'ESTABLISHED')
        decision = aggregate_findings((mismatch,), (candid,), coverage())
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')
        self.assertIn('misstatement_policy_unresolved', decision.reasons)
        self.assertEqual(decision.matches, (mismatch,))
        self.assertEqual(decision.disclosures, (candid,))

    def test_material_known_omission_requires_complete_scoped_coverage(self):
        omission = DisclosureFinding('event:1', 'NOT_FOUND', (), 'MATERIAL', 'ESTABLISHED')
        self.assertEqual(aggregate_findings((), (omission,), coverage()).assessment, 'EVASIVE')
        incomplete = replace(coverage(), complete=False, gaps=('missing_call',))
        self.assertEqual(aggregate_findings((), (omission,), incomplete).assessment, 'INSUFFICIENT_EVIDENCE')

    def test_candid_material_events_can_pass_only_with_resolved_inputs(self):
        candid = DisclosureFinding('event:1', 'ACKNOWLEDGED', ('claim:1',), 'MATERIAL', 'ESTABLISHED')
        self.assertEqual(aggregate_findings((), (candid,), coverage()).assessment, 'TRANSPARENT')
        unresolved = ClaimEvidenceMatch('claim:2', None, 'UNKNOWN', 'INCONCLUSIVE', 'unknown_metric')
        self.assertEqual(aggregate_findings((unresolved,), (candid,), coverage()).assessment,
                         'INSUFFICIENT_EVIDENCE')

    def test_coverage_is_only_named_calls_and_missing_date_remains_unknown(self):
        transcripts = tuple(Transcript(p, f'earnings_call_{p.lower()}.md', Source(
            f'doc:{p}', 'x', 'read_document', {}, 'CEO: We discussed results.')) for p in PERIODS)
        result = communication_coverage(transcripts)
        self.assertFalse(result.complete)
        self.assertIn('unknown_communication_date', result.gaps)
        self.assertEqual(result.scope, 'four_supplied_earnings_calls')
