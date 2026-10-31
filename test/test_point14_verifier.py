import json
from decimal import Decimal
import unittest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

from fisher_agent.point14.model_gateway import ModelGateway
from fisher_agent.point14.records import Diagnostics, ManagementClaim
from fisher_agent.point14.transparency_verifier import TransparencyVerifier
from fisher_agent.point14.financial_evidence_extractor import FinancialEvidenceExtractor
from test_point14_financial import financial_sql


def finding(period, classification='ACKNOWLEDGED', material=True, claim_ids=None,
            basis='OPEN_DISCUSSION'):
    return {'metric_id': f'{period}:revenue:qoq', 'classification': classification,
            'material': material, 'claim_ids': claim_ids if claim_ids is not None else [f'claim:{period}:1'],
            'basis': basis}


def judgement(assessment='TRANSPARENT', **changes):
    value = {'assessment': assessment, 'comparisons': [finding(p) for p in ('2025Q3','2025Q4','2026Q1','2026Q2')]}
    value.update(changes)
    return value


class VerifierTests(unittest.IsolatedAsyncioTestCase):
    async def run_verifier(self, candidates, adjudicate=False):
        snapshot = await FinancialEvidenceExtractor().extract('x', financial_sql)
        claims = tuple(ManagementClaim(f'claim:{p}:1', f'earnings_call_{p.lower()}.md',
                       p, 'revenue', 'We discussed demand and the shortfall.', 'acknowledges_setback')
                       for p in ('2025Q3','2025Q4','2026Q1','2026Q2'))
        model = AsyncMock()
        model.ainvoke.side_effect = [AIMessage(content=json.dumps(c)) for c in candidates]
        diagnostics = Diagnostics()
        verifier = TransparencyVerifier(ModelGateway(model, diagnostics))
        assessment = await verifier.verify(snapshot, claims)
        if adjudicate and assessment.assessment == 'UNCERTAIN':
            assessment = await verifier.adjudicate(snapshot, claims, assessment)
        return assessment, model, diagnostics

    async def test_acknowledged_decline_and_cost_pressure_can_pass(self):
        for metric in ('revenue', 'operating_costs'):
            proposal = judgement()
            for item in proposal['comparisons']:
                item['metric_id'] = item['metric_id'].replace('revenue', metric)
            result, _, _ = await self.run_verifier([proposal])
            self.assertEqual(result.assessment, 'TRANSPARENT')

    async def test_material_contradiction_or_omission_can_fail(self):
        for classification, basis, ids in [('CONTRADICTED','FACTUAL_CONFLICT',['claim:2025Q3:1']),
                                            ('UNADDRESSED','MATERIAL_OMISSION',[])]:
            proposal = judgement('EVASIVE')
            proposal['comparisons'][0] = finding('2025Q3', classification, True, ids, basis)
            result, _, _ = await self.run_verifier([proposal])
            self.assertEqual(result.assessment, 'EVASIVE')

    async def test_no_material_setback_does_not_imply_evasiveness(self):
        proposal = judgement(comparisons=[finding(p, 'NOT_APPLICABLE', False, [], 'NO_MATERIAL_SETBACK')
                   for p in ('2025Q3','2025Q4','2026Q1','2026Q2')])
        result, _, _ = await self.run_verifier([proposal])
        self.assertEqual(result.assessment, 'TRANSPARENT')

    async def test_uncertainty_has_one_final_adjudication(self):
        initial = judgement('UNCERTAIN')
        initial['comparisons'][0] = finding('2025Q3', 'UNVERIFIABLE', True,
                                            ['claim:2025Q3:1'], 'AMBIGUOUS_EVIDENCE')
        result, model, diagnostics = await self.run_verifier([initial, judgement()], adjudicate=True)
        self.assertEqual(result.assessment, 'TRANSPARENT')
        self.assertEqual(model.ainvoke.call_count, 2)
        self.assertEqual(diagnostics.adjudications, 1)

    async def test_final_transparent_cannot_keep_material_unverifiable_findings(self):
        initial = judgement('UNCERTAIN')
        initial['comparisons'][0] = finding('2025Q3', 'UNVERIFIABLE', True,
                                            ['claim:2025Q3:1'], 'AMBIGUOUS_EVIDENCE')
        unresolved = {**initial, 'assessment': 'TRANSPARENT'}
        with self.assertRaises(ValueError):
            await self.run_verifier([initial, unresolved, unresolved], adjudicate=True)

    async def test_payload_provides_decimal_million_equivalents_without_changing_sources(self):
        snapshot = await FinancialEvidenceExtractor().extract('x', financial_sql)
        payload = TransparencyVerifier(None).payload(snapshot, (), ())
        revenue = next(m for m in payload['financial_metrics']
                       if m['evidence_id'] == '2025Q3:revenue:qoq')
        self.assertEqual(revenue['USD_millions']['value'], Decimal('0.15'))
        self.assertEqual(revenue['USD_millions']['comparison_value'], Decimal('0.18'))
        self.assertEqual(revenue['USD_millions']['absolute_change'], Decimal('-0.03'))
        self.assertEqual(revenue['USD_millions']['value_rounded_1dp'], Decimal('0.2'))
        self.assertEqual(revenue['value'], 150)
        margin = next(m for m in payload['financial_metrics']
                      if m['evidence_id'] == '2025Q3:operating_margin_pct:qoq')
        self.assertNotIn('USD_millions', margin)
        self.assertEqual(snapshot.metrics[0].value, 150)

    async def test_rejects_unsupported_metrics_numbers_cross_quarter_and_inconsistent_verdicts(self):
        proposals = []
        invented = judgement(); invented['comparisons'][0]['metric_id'] = 'made_up:500'
        proposals.append(invented)
        numbers = judgement(); numbers['profit'] = 999999
        proposals.append(numbers)
        cross = judgement(); cross['comparisons'][0]['claim_ids'] = ['claim:2025Q4:1']
        proposals.append(cross)
        proposals.append(judgement('EVASIVE'))
        omitted = judgement(); omitted['comparisons'] = omitted['comparisons'][:1]
        proposals.append(omitted)
        for candidate in proposals:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                await self.run_verifier([candidate, candidate])

    async def test_malformed_output_can_recover_once(self):
        result, _, diagnostics = await self.run_verifier([{'broken': True}, judgement()])
        self.assertEqual(result.assessment, 'TRANSPARENT')
        self.assertEqual(diagnostics.parsing_retries, 1)
