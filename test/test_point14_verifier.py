import json
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

from fisher_agent.point14.claim_evidence_matcher import evidence_facts
from fisher_agent.point14.disclosure_rules import prepare_events
from fisher_agent.point14.financial_evidence_extractor import FinancialEvidenceExtractor
from fisher_agent.point14.model_gateway import ModelGateway
from fisher_agent.point14.records import Diagnostics, ManagementClaim, PERIODS, Source, SourcedProposition, Transcript
from fisher_agent.point14.transparency_verifier import TransparencyVerifier
from test_point14_financial import financial_sql

DATES = dict(zip(PERIODS, ('2025-10-29', '2026-02-25', '2026-04-28', '2026-07-29')))


def claims():
    return tuple(ManagementClaim(f'claim:{p}:1', f'earnings_call_{p.lower()}.md', p,
        'revenue', f'Revenue was USD {value} thousand.', 'favourable',
        SourcedProposition('company', 'revenue', p, 'level', Decimal(value), 'USD_thousands',
                           'level', certainty='asserted', measurement_definition='sales_revenue',
                           definition_quotation='Revenue'), 'x', f'doc:{p}', 'CEO', DATES[p])
        for p, value in zip(PERIODS, ('150', '100', '100', '90')))


def transcripts():
    return tuple(Transcript(p, f'earnings_call_{p.lower()}.md', Source(f'doc:{p}', 'x',
        'read_document', {'name': f'earnings_call_{p.lower()}.md'},
        f'Date: {DATES[p]}\n\nCEO: Revenue was discussed.')) for p in PERIODS)


def judgement(snapshot, supplied_claims):
    return {'matches': [{'claim_id': c.evidence_id,
                         'fact_id': f'{c.proposition.period}:{c.proposition.metric}:level'}
                        for c in supplied_claims],
            'disclosures': [{'event_id': event.evidence_id, 'relation': 'NOT_FOUND',
                'claim_ids': [], 'materiality': 'UNKNOWN', 'materiality_claim_ids': [],
                'knowledge': 'UNKNOWN', 'knowledge_claim_ids': []}
                for event in prepare_events(evidence_facts(snapshot))]}


class VerifierTests(unittest.IsolatedAsyncioTestCase):
    async def run_verifier(self, mutate=None, repair=False):
        snapshot = await FinancialEvidenceExtractor().extract('x', financial_sql)
        supplied_claims = claims()
        valid = judgement(snapshot, supplied_claims)
        candidate = mutate(json.loads(json.dumps(valid))) if mutate else valid
        model = AsyncMock()
        model.ainvoke.side_effect = [AIMessage(content=json.dumps(item))
            for item in ([candidate, valid] if repair else [candidate, candidate])]
        diagnostics = Diagnostics()
        verifier = TransparencyVerifier(ModelGateway(model, diagnostics))
        result = await verifier.verify(snapshot, supplied_claims, transcripts())
        return result, model, diagnostics

    async def test_matched_truth_does_not_upgrade_unknown_disclosure_to_transparent(self):
        result, model, _ = await self.run_verifier()
        self.assertEqual(result.assessment, 'INSUFFICIENT_EVIDENCE')
        self.assertTrue(all(m.relation == 'SUPPORTED' for m in result.matches))
        self.assertTrue(all(d.knowledge == 'UNKNOWN' for d in result.disclosures))
        self.assertEqual(model.ainvoke.call_count, 1)

    async def test_unproved_materiality_and_knowledge_remain_unknown(self):
        def mutate(value):
            value['disclosures'][0].update(materiality='MATERIAL', knowledge='ESTABLISHED')
            return value
        result, _, _ = await self.run_verifier(mutate)
        self.assertEqual(result.assessment, 'INSUFFICIENT_EVIDENCE')
        self.assertEqual(result.disclosures[0].materiality, 'UNKNOWN')
        self.assertEqual(result.disclosures[0].knowledge, 'UNKNOWN')

    async def test_wrong_metric_alignment_is_unmatched_not_a_contradiction(self):
        def mutate(value):
            value['matches'][0]['fact_id'] = '2025Q3:operating_profit:level'
            return value
        result, _, _ = await self.run_verifier(mutate)
        self.assertEqual(result.matches[0].relation, 'UNMATCHED')
        self.assertEqual(result.assessment, 'INSUFFICIENT_EVIDENCE')

    async def test_invented_or_missing_references_are_rejected_with_one_recovery(self):
        def mutate(value):
            value['matches'][0]['fact_id'] = 'invented'
            return value
        result, model, diagnostics = await self.run_verifier(mutate, repair=True)
        self.assertEqual(result.assessment, 'INSUFFICIENT_EVIDENCE')
        self.assertEqual(model.ainvoke.call_count, 2)
        self.assertEqual(diagnostics.parsing_retries, 1)
        for mutator in (mutate, lambda value: {**value, 'matches': []},
                         lambda value: {**value, 'disclosures': []}):
            with self.assertRaises(ValueError):
                await self.run_verifier(mutator)

    async def test_duplicate_and_cross_event_sources_do_not_create_acknowledgement(self):
        def mutate(value):
            value['disclosures'][0].update(relation='ACKNOWLEDGED', claim_ids=['claim:2026Q2:1'])
            return value
        result, _, _ = await self.run_verifier(mutate)
        self.assertEqual(result.disclosures[0].relation, 'INCONCLUSIVE')
        self.assertEqual(result.assessment, 'INSUFFICIENT_EVIDENCE')

    async def test_complete_payload_has_direct_return_counts_and_bounded_claim_scope(self):
        snapshot = await FinancialEvidenceExtractor().extract('x', financial_sql)
        payload = TransparencyVerifier(None).payload(snapshot, claims(), transcripts())
        direct = next(f for f in payload['facts'] if f['evidence_id'] == '2026Q1:return_rate:level')
        self.assertEqual(direct['denominator'], 1000)
        self.assertEqual(direct['value'], Decimal('2.600'))
        self.assertEqual(payload['coverage']['claim_extraction_scope'], 'bounded_candidates_not_exhaustive')
        self.assertEqual(len(payload['full_transcripts']), 4)
