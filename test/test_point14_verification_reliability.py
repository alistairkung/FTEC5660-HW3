"""Replay sourced verification proposals without labels or model calls."""
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage

from fisher_agent.point14.records import (FinancialMetric, FinancialSnapshot, ManagementClaim,
    QuarterlyReturns, Source, SourcedProposition, Transcript, EvidenceError, Diagnostics)
from fisher_agent.point14.model_gateway import ModelGateway
from fisher_agent.point14.claim_evidence_matcher import evidence_facts, match_claim
from fisher_agent.point14.transparency_verifier import TransparencyVerifier, Verification, render_reason

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/point14_cobalt_verification.json').read_text())


def recorded_evidence():
    raw = FIXTURE['financial']
    metrics = []
    for original in raw['metrics']:
        row = dict(original)
        for key in ('value', 'comparison_value', 'absolute_change', 'percentage_change'):
            if row[key] is not None:
                row[key] = Decimal(row[key])
        metrics.append(FinancialMetric(**row))
    returns = []
    for original in raw['returns']:
        row = dict(original)
        for key in ('units_shipped', 'units_returned', 'rate_pct'):
            if row[key] is not None:
                row[key] = Decimal(row[key])
        returns.append(QuarterlyReturns(**row))
    financial = FinancialSnapshot(tuple(metrics), Source(**raw['source']), tuple(returns))
    claims = []
    for original in FIXTURE['claims']:
        row = dict(original)
        proposition = dict(row['proposition'])
        proposition['qualifiers'] = tuple(proposition['qualifiers'])
        if proposition['value'] is not None:
            proposition['value'] = Decimal(proposition['value'])
        row['proposition'] = SourcedProposition(**proposition)
        claims.append(ManagementClaim(**row))
    source_fixture = json.loads((Path(__file__).parent / 'fixtures/point14_cobalt_normalization.json').read_text())
    docs = tuple(Transcript(d['period'], d['name'], Source(**d['source']))
                 for d in source_fixture['transcripts'])
    return financial, tuple(claims), docs


class VerificationReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.financial, self.claims, self.docs = recorded_evidence()
        self.verifier = TransparencyVerifier(None)

    def test_recorded_extra_events_rejected_with_specific_code(self):
        first = Verification.model_validate_json(FIXTURE['responses'][0]['content'])
        with self.assertRaisesRegex(EvidenceError, '^unknown_event_reference$'):
            self.verifier.validate(first, self.financial, self.claims, self.docs)

    def test_independent_admission_survives_mixed_commitment_reference(self):
        proposal = Verification.model_validate_json(FIXTURE['responses'][1]['content'])
        decision = self.verifier.validate(proposal, self.financial, self.claims, self.docs)
        finding = next(d for d in decision.disclosures if d.event_id == 'event:2025Q3:return_rate')
        self.assertEqual(finding.relation, 'ACKNOWLEDGED')
        self.assertEqual(finding.claim_ids, ('claim:2025Q3:2',))
        self.assertEqual(finding.rejected_claim_ids, ('claim:2025Q3:3',))
        self.assertIn('non_acknowledging_reference', finding.diagnostics)
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')

    def test_recorded_responses_immutable(self):
        for response in FIXTURE['responses']:
            self.assertEqual(hashlib.sha256(response['content'].encode()).hexdigest(), response['sha256'])

    def test_measured_returns_direction_does_not_verify_causal_qualifier(self):
        admission = next(c for c in self.claims if c.evidence_id == 'claim:2025Q3:2')
        proposition = replace(admission.proposition, unit='percent', basis='qoq',
            comparator_period='2025Q2', measurement_definition='units_returned/units_shipped')
        claim = replace(admission, proposition=proposition)
        fact = next(f for f in evidence_facts(self.financial) if f.evidence_id == '2025Q3:return_rate:qoq')
        match = match_claim(claim, fact)
        self.assertEqual(match.relation, 'SUPPORTED')
        self.assertEqual(match.unverified_qualifiers, ('because of a faulty batch of labelling line parts',))
        proposal = Verification.model_validate_json(FIXTURE['responses'][1]['content'])
        decision = self.verifier.validate(proposal, self.financial,
            tuple(claim if c.evidence_id == claim.evidence_id else c for c in self.claims), self.docs)
        summary = render_reason(replace(decision, matches=(match,)), self.financial, (claim,))
        self.assertIn('proposition only', summary)
        self.assertIn('qualifiers unverified', summary)
        self.assertEqual(claim.quotation, admission.quotation)

    def test_missing_duplicate_and_unknown_claim_references_still_reject(self):
        original = json.loads(FIXTURE['responses'][1]['content'])
        for change, code in (
            ('missing', 'incomplete_event_coverage'),
            ('duplicate', 'duplicate_event_reference'),
            ('unknown_claim', 'unknown_claim_reference'),
        ):
            proposal = json.loads(json.dumps(original))
            if change == 'missing':
                proposal['disclosures'].pop()
            elif change == 'duplicate':
                proposal['disclosures'].append(proposal['disclosures'][0])
            else:
                proposal['disclosures'][0]['claim_ids'] = ['fabricated:claim']
            with self.subTest(change=change), self.assertRaisesRegex(EvidenceError, '^'+code+'$'):
                self.verifier.validate(Verification.model_validate(proposal), self.financial, self.claims, self.docs)

    def test_wrong_period_metric_and_causal_references_do_not_acknowledge(self):
        original = json.loads(FIXTURE['responses'][1]['content'])
        admission = next(c for c in self.claims if c.evidence_id == 'claim:2025Q3:2')
        for changes in ({'period':'2025Q4'}, {'metric':'operating_profit'}, {'assertion_type':'causal'}):
            invalid = replace(admission, proposition=replace(admission.proposition, **changes))
            claims = tuple(invalid if c.evidence_id == invalid.evidence_id else c for c in self.claims)
            with self.subTest(changes=changes):
                decision = self.verifier.validate(Verification.model_validate(original), self.financial, claims, self.docs)
                finding = next(d for d in decision.disclosures if d.event_id == 'event:2025Q3:return_rate')
                self.assertEqual(finding.relation, 'INCONCLUSIVE')
                self.assertEqual(finding.claim_ids, ())
                self.assertEqual(finding.knowledge, 'UNKNOWN')
                self.assertEqual(finding.rejected_claim_ids, ('claim:2025Q3:2','claim:2025Q3:3'))


class VerificationRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_prepared_events_does_not_authorize_invented_events(self):
        financial, _, docs = recorded_evidence()
        financial = replace(financial, metrics=(), returns=())
        model = AsyncMock(ainvoke=AsyncMock(return_value=AIMessage(content='{"matches":[],"disclosures":[]}')))
        diagnostics = Diagnostics()
        decision = await TransparencyVerifier(ModelGateway(model, diagnostics)).verify(financial, (), docs)
        self.assertEqual(decision.disclosures, ())
        self.assertEqual(diagnostics.model_calls, 1)
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')

    async def test_recorded_extra_ids_recover_once_with_exact_prepared_schema(self):
        financial, claims, docs = recorded_evidence()
        model = AsyncMock(ainvoke=AsyncMock(side_effect=[AIMessage(content=r['content'])
                                                        for r in FIXTURE['responses']]))
        diagnostics = Diagnostics()
        decision = await TransparencyVerifier(ModelGateway(model, diagnostics)).verify(financial, claims, docs)
        self.assertEqual(diagnostics.model_calls, 2)
        self.assertEqual(diagnostics.parsing_retries, 1)
        self.assertEqual(diagnostics.validation_rejections, ['unknown_event_reference'])
        messages = model.ainvoke.call_args_list[0].args[0]
        schema = json.loads(messages[0].content.split('matching this schema:\n')[1])
        allowed = schema['$defs']['PreparedDisclosure']['properties']['event_id']['enum']
        payload = json.loads(messages[1].content)
        self.assertEqual(set(allowed), set(payload['prepared_event_ids']))
        self.assertEqual(len(allowed), 21)
        self.assertNotIn('event:2026Q1:return_rate', allowed)
        self.assertEqual(decision.assessment, 'INSUFFICIENT_EVIDENCE')
