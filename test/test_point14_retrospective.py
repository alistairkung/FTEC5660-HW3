"""Evidence-level invariants from recorded tool outputs; no expected company labels."""
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import re
import unittest

from fisher_agent.point14.claim_evidence_matcher import evidence_facts, match_claim
from fisher_agent.point14.disclosure_rules import aggregate_findings, communication_coverage, prepare_events
from fisher_agent.point14.management_claim_extractor import source_span
from fisher_agent.point14.records import (ClaimEvidenceMatch, FinancialMetric, FinancialSnapshot,
    ManagementClaim, QuarterlyReturns, Source, SourcedProposition, Transcript)
from fisher_agent.point14.transparency_verifier import TransparencyVerifier, Verification

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/point14_retrospective.json').read_text())


def evidence(name):
    row = FIXTURES[name]
    metrics = []
    for item in row['metrics']:
        item = dict(item)
        for key in ('value', 'comparison_value', 'absolute_change', 'percentage_change'):
            item[key] = Decimal(item[key]) if item[key] is not None else None
        metrics.append(FinancialMetric(**item))
    returns = []
    for line in row['returns_source']['raw'].splitlines()[1:]:
        period, rows, months, shipped, returned, valid, _ = [part.strip() for part in line.split('|')]
        assert (rows, months, valid) == ('3', '3', '3')
        returns.append(QuarterlyReturns(period, Decimal(shipped), Decimal(returned),
            Decimal(returned) / Decimal(shipped) * 100, row['returns_source']['evidence_id']))
    snapshot = FinancialSnapshot(tuple(metrics), Source(**row['financial_source']), tuple(returns))
    docs = tuple(Transcript(d['period'], d['name'], Source(**d['source'])) for d in row['transcripts'])
    return snapshot, docs


def sourced(name, period, quotation, proposition, kind='favourable'):
    _, docs = evidence(name)
    doc = next(d for d in docs if d.period == period)
    quote, speaker, start, end = source_span(quotation, doc.source.raw)
    if proposition.metric == 'revenue':
        proposition = replace(proposition, measurement_definition='sales_revenue', definition_quotation='Revenue')
    dated = re.search(r'^Date: (\d{4}-\d{2}-\d{2})', doc.source.raw, re.MULTILINE).group(1)
    return ManagementClaim(f'claim:{period}:{proposition.metric}', doc.name, period, proposition.metric,
        quote, kind, proposition, name, doc.source.evidence_id, speaker, dated, start, end)


def proposals(snapshot, claims):
    return {'matches': [{'claim_id': c.evidence_id,
                          'fact_id': f'{c.proposition.period}:{c.proposition.metric}:level'} for c in claims],
            'disclosures': [{'event_id': e.evidence_id, 'relation': 'NOT_FOUND', 'claim_ids':[],
                'materiality':'UNKNOWN', 'materiality_claim_ids':[], 'knowledge':'UNKNOWN',
                'knowledge_claim_ids':[]} for e in prepare_events(evidence_facts(snapshot))]}


class RetrospectiveTests(unittest.TestCase):
    def test_cobalt_returns_admission_and_reduced_profit_are_different_propositions(self):
        snapshot, docs = evidence('cobalt_holdings')
        admission = sourced('cobalt_holdings', '2025Q3',
            'Returns rose sharply this quarter because of a faulty batch of labelling line parts.',
            SourcedProposition('company', 'return_rate', '2025Q3', 'change', unit='percent',
                direction='increased', qualifiers=('sharply',), certainty='asserted'), 'acknowledges_setback')
        profit = next(f for f in evidence_facts(snapshot) if f.evidence_id == '2025Q3:operating_profit:qoq')
        self.assertEqual(match_claim(admission, profit).relation, 'UNMATCHED')
        proposal = proposals(snapshot, (admission,))
        proposal['matches'][0]['fact_id'] = profit.evidence_id
        item = next(d for d in proposal['disclosures'] if d['event_id'] == 'event:2025Q3:return_rate')
        item.update(relation='ACKNOWLEDGED', claim_ids=[admission.evidence_id],
                    knowledge='ESTABLISHED', knowledge_claim_ids=[admission.evidence_id])
        decision = TransparencyVerifier(None).validate(Verification.model_validate(proposal), snapshot, (admission,), docs)
        finding = next(d for d in decision.disclosures if d.event_id == item['event_id'])
        self.assertEqual(finding.relation, 'ACKNOWLEDGED')
        self.assertEqual(finding.knowledge, 'ESTABLISHED')
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')

    def test_kestrel_direct_ratio_of_sums_does_not_invent_a_low_threshold(self):
        snapshot, _ = evidence('kestrel_technologies')
        direct = next(f for f in evidence_facts(snapshot) if f.evidence_id == '2026Q1:return_rate:level')
        self.assertEqual(direct.denominator, 7432)
        self.assertEqual(direct.value.quantize(Decimal('0.0001')), Decimal('5.0861'))
        self.assertEqual(direct.source_id, 'review:returns:kestrel_technologies')
        low = sourced('kestrel_technologies', '2026Q1', 'Returns stayed low and product quality was steady.',
            SourcedProposition('company', 'return_rate', '2026Q1', 'level', unit='percent', basis='level',
                              direction='low', qualifiers=('low',), certainty='asserted'))
        self.assertEqual(match_claim(low, direct).relation, 'INCONCLUSIVE')
        wrong_quarter = replace(direct, period='2025Q4')
        self.assertEqual(match_claim(low, wrong_quarter).relation, 'UNMATCHED')

    def test_dunmore_misstatement_and_candid_other_quarter_are_both_preserved(self):
        snapshot, docs = evidence('dunmore_holdings')
        revenue = sourced('dunmore_holdings', '2026Q1', 'Revenue for the quarter was USD 265.7 million.',
            SourcedProposition('company', 'revenue', '2026Q1', 'level', Decimal('265.7'), 'USD_millions',
                              'level', certainty='asserted'))
        admission = sourced('dunmore_holdings', '2025Q3',
            'Returns rose sharply this quarter because of a faulty batch of camera module parts.',
            SourcedProposition('company', 'return_rate', '2025Q3', 'change', unit='percent',
                direction='increased', qualifiers=('sharply',), certainty='asserted'), 'acknowledges_setback')
        proposal = proposals(snapshot, (revenue, admission))
        target = next(d for d in proposal['disclosures'] if d['event_id'] == 'event:2025Q3:return_rate')
        target.update(relation='ACKNOWLEDGED', claim_ids=[admission.evidence_id])
        decision = TransparencyVerifier(None).validate(Verification.model_validate(proposal), snapshot,
                                                      (revenue, admission), docs)
        self.assertEqual(decision.matches[0].relation, 'CONTRADICTED')
        self.assertTrue(any(d.relation == 'ACKNOWLEDGED' and admission.evidence_id in d.claim_ids
                            for d in decision.disclosures))
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')
        self.assertIn('misstatement_policy_unresolved', decision.reasons)

    def test_ashgrove_unknown_matching_cannot_become_transparent(self):
        _, docs = evidence('ashgrove_labs')
        unresolved = ClaimEvidenceMatch('recorded:unknown', None, 'UNKNOWN', 'INCONCLUSIVE', 'unknown_comparator')
        decision = aggregate_findings((unresolved,), (), communication_coverage(docs))
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')

    def test_aurel_decline_and_scoped_absence_do_not_prove_concealment(self):
        snapshot, docs = evidence('aurel_systems')
        proposal = proposals(snapshot, ())
        decision = TransparencyVerifier(None).validate(Verification.model_validate(proposal), snapshot, (), docs)
        self.assertTrue(decision.disclosures)
        self.assertTrue(all(d.knowledge == 'UNKNOWN' for d in decision.disclosures))
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')
        incomplete = communication_coverage(docs[:-1])
        self.assertFalse(incomplete.complete)
