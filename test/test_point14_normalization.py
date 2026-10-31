"""Replay immutable observed outputs through the extraction contract, without APIs."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage

from fisher_agent.point14.management_claim_extractor import ManagementClaimExtractor
from fisher_agent.point14.model_gateway import ModelGateway
from fisher_agent.point14.records import Diagnostics, Source, Transcript
from fisher_agent.point14.claim_evidence_matcher import match_claim
from fisher_agent.point14.records import EvidenceFact
from decimal import Decimal

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/point14_cobalt_normalization.json').read_text())


class NormalizationTests(unittest.IsolatedAsyncioTestCase):
    def transcripts(self):
        return tuple(Transcript(d['period'], d['name'], Source(**d['source'])) for d in FIXTURE['transcripts'])

    async def extract(self, content):
        model = AsyncMock(ainvoke=AsyncMock(return_value=AIMessage(content=content)))
        diagnostics = Diagnostics()
        claims = await ManagementClaimExtractor(ModelGateway(model, diagnostics)).extract(self.transcripts())
        return claims, diagnostics, model

    async def test_both_recorded_responses_retain_all_sourced_claims_without_invented_numbers(self):
        for response in FIXTURE['responses']:
            with self.subTest(observation=response['observation_id']):
                self.assertEqual(hashlib.sha256(response['content'].encode()).hexdigest(), response['sha256'])
                claims, diagnostics, model = await self.extract(response['content'])
                self.assertEqual(len(claims), 12)
                self.assertEqual(model.ainvoke.call_count, 1)
                self.assertEqual([c.evidence_id for c in claims],
                    [f'claim:{p}:{n}' for p in ('2025Q3','2025Q4','2026Q1','2026Q2') for n in (1,2,3)])
                revenue = [c for c in claims if c.proposition.metric == 'revenue']
                self.assertEqual(len(revenue), 4)
                self.assertTrue(all(c.proposition.measurement_definition == 'sales_revenue' for c in revenue))
                self.assertTrue(all(c.proposition.definition_quotation is None for c in revenue))
                qualitative = [c for c in claims if c.proposition.qualitative_text in ('low','negligible')]
                self.assertEqual(len(qualitative), 3)
                self.assertTrue(all(c.proposition.value is None for c in qualitative))
                by_doc = {d.name:d for d in self.transcripts()}
                for claim in claims:
                    self.assertEqual(by_doc[claim.document].source.raw[claim.span_start:claim.span_end], claim.quotation)

    async def single(self, quote, proposition):
        document = Transcript('2025Q3', 'earnings_call_2025q3.md', Source(
            'doc:q3', 'synthetic', 'read_document', {}, 'Date: 2025-10-29\n\nCEO: ' + quote))
        content = json.dumps({'claims':[{'document':document.name, 'period':document.period,
            'topic':'revenue', 'quotation':quote, 'kind':'favourable', 'proposition':proposition}]})
        model = AsyncMock(ainvoke=AsyncMock(return_value=AIMessage(content=content)))
        diagnostics = Diagnostics()
        claims = await ManagementClaimExtractor(ModelGateway(model, diagnostics)).extract((document,))
        return claims[0], diagnostics

    async def test_general_explicit_qualitative_and_ambiguous_definitions_remain_non_numeric(self):
        claim, _ = await self.single('Demand remains patchy.', {'subject':'company', 'metric':'demand',
            'assertion_type':'qualitative', 'qualitative_text':'patchy', 'period':'2025Q3', 'certainty':'asserted'})
        self.assertIsNone(claim.proposition.value)
        self.assertEqual(claim.proposition.qualitative_text, 'patchy')
        for quote, qualifiers, subject in (
            ('Gross revenue was USD 10.0 million.', ['Gross'], 'company'),
            ('Net revenue was USD 10.0 million.', ['Net'], 'company'),
            ('Product A revenue was USD 10.0 million.', [], 'product:A'),
        ):
            with self.subTest(quote=quote):
                claim, _ = await self.single(quote, {'subject':subject, 'metric':'revenue', 'period':'2025Q3',
                    'assertion_type':'level', 'value_text':'10.0', 'unit':'USD_millions', 'basis':'level',
                    'measurement_definition':'sales_revenue', 'definition_quotation':None,
                    'qualifiers':qualifiers, 'certainty':'asserted'})
                self.assertIsNone(claim.proposition.measurement_definition)

    async def test_directional_alias_reaches_same_comparison_and_nonfactual_types_do_not(self):
        proposition = {'subject':'company', 'metric':'revenue', 'period':'2025Q3', 'assertion_type':'directional',
            'direction':'increased', 'unit':'USD_thousands', 'basis':'qoq', 'comparator_period':'2025Q2',
            'measurement_definition':'sales_revenue', 'definition_quotation':'Revenue', 'certainty':'asserted'}
        claim, _ = await self.single('Revenue increased quarter on quarter.', proposition)
        fact = EvidenceFact('revenue:q3', 'synthetic', 'company', 'revenue', '2025Q3', 'qoq', Decimal(110),
            'USD_thousands', 'sql', '2025Q2', Decimal(100), Decimal(10), Decimal(10),
            measurement_definition='sales_revenue')
        self.assertEqual(match_claim(claim, fact).relation, 'SUPPORTED')
        for category in ('causal', 'forecast', 'commitment'):
            claim, _ = await self.single('Revenue increased quarter on quarter.',
                                         {**proposition, 'assertion_type':category})
            self.assertEqual(claim.proposition.assertion_type, category)
            self.assertEqual(match_claim(claim, fact).relation, 'INCONCLUSIVE')

    async def test_compound_assertion_subspan_preserves_parent_citation_and_causal_uncertainty(self):
        quote = 'Returns rose because of a batch defect. We will replace affected units.'
        selected = 'Returns rose because of a batch defect.'
        claim, _ = await self.single(quote, {'subject':'company', 'metric':'return_rate', 'period':'2025Q3',
            'assertion_type':'causal', 'assertion_quotation':selected, 'certainty':'asserted'})
        self.assertEqual(claim.quotation, quote)
        self.assertEqual(claim.evidence_id, 'claim:2025Q3:1')
        self.assertEqual(claim.source_id, 'doc:q3')
        self.assertEqual(claim.proposition.assertion_quotation, selected)
        with self.assertRaises(ValueError):
            await self.single(quote, {'assertion_type':'causal', 'assertion_quotation':'Invented cause.'})

    async def test_subspan_cannot_remove_parent_scope_or_borrow_other_clause_grounding(self):
        selected = 'Revenue for the quarter was USD 10.0 million.'
        proposition = {'subject':'company', 'metric':'revenue', 'period':'2025Q3', 'assertion_type':'level',
            'value_text':'10.0', 'unit':'USD_millions', 'basis':'level', 'certainty':'asserted',
            'measurement_definition':'sales_revenue', 'assertion_quotation':selected}
        claim, _ = await self.single('Within the devices division, ' + selected, proposition)
        self.assertIsNone(claim.proposition.measurement_definition)
        for extra in ({'definition_quotation':'net of returns'}, {'qualifiers':['net of returns']}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                await self.single(selected + ' Other figures are net of returns.', {**proposition, **extra})

    async def test_repeated_assertion_is_resolved_inside_its_validated_parent_turn(self):
        text = 'CEO: Revenue increased.\n\nCFO: Revenue increased. Costs fell.'
        document = Transcript('2025Q3', 'earnings_call_2025q3.md', Source('doc:q3','x','read_document',{},text))
        content = json.dumps({'claims':[{'document':document.name,'period':document.period,'topic':'revenue',
            'quotation':'Revenue increased. Costs fell.','kind':'favourable',
            'proposition':{'assertion_type':'directional','assertion_quotation':'Revenue increased.'}}]})
        model = AsyncMock(ainvoke=AsyncMock(return_value=AIMessage(content=content)))
        result = await ManagementClaimExtractor(ModelGateway(model, Diagnostics())).extract((document,))
        self.assertEqual(result[0].speaker, 'CFO')
        self.assertEqual(result[0].proposition.assertion_quotation, 'Revenue increased.')

    async def test_qualitative_family_cannot_hide_invented_numbers_or_arbitrary_legacy_values(self):
        with self.assertRaises(ValueError):
            await self.single('Returns stayed low.', {'assertion_type':'qualitative',
                'qualitative_text':'low','value_text':'999.9','unit':'percent','direction':'low'})
        with self.assertRaises(ValueError):
            await self.single('Management called the batch garbage.', {'assertion_type':'level',
                'value_text':'garbage','direction':'low'})

    async def test_numeric_recovery_names_the_finite_failure_without_echoing_model_output(self):
        valid = FIXTURE['responses'][0]['content']
        invalid = json.loads(valid)
        invalid['claims'][0]['proposition']['value_text'] = '999.9'
        model = AsyncMock(ainvoke=AsyncMock(side_effect=[AIMessage(content=json.dumps(invalid)), AIMessage(content=valid)]))
        diagnostics = Diagnostics()
        claims = await ManagementClaimExtractor(ModelGateway(model, diagnostics)).extract(self.transcripts())
        self.assertEqual(len(claims),12)
        self.assertEqual(diagnostics.validation_rejections, ['unsupported_numeric_value'])
        self.assertEqual(diagnostics.parsing_retries,1)
        repair = model.ainvoke.call_args_list[1].args[0][-1].content
        self.assertIn('unsupported_numeric_value',repair)
        self.assertIn('qualitative_text',repair)
        self.assertNotIn('999.9',repair)

    async def test_explicit_qualitative_cannot_also_carry_a_sourced_numeric_value(self):
        with self.assertRaises(ValueError):
            await self.single('Returns were low at 5 percent.', {'assertion_type':'qualitative',
                'qualitative_text':'low','value_text':'5','unit':'percent','direction':'low'})

    async def test_missing_numeric_level_is_explicitly_incomplete_and_legacy_qualitative_is_preserved(self):
        claim, diagnostics = await self.single('Revenue was USD 10 million.', {
            'subject':'company','metric':'revenue','period':'2025Q3','assertion_type':'level',
            'unit':'USD_millions','basis':'level','certainty':'asserted',
            'measurement_definition':'sales_revenue','definition_quotation':'Revenue'})
        self.assertIsNone(claim.proposition.value)
        self.assertIn('incomplete_numeric_level',diagnostics.normalization_notes)
        fact = EvidenceFact('revenue:q3','synthetic','company','revenue','2025Q3','level',Decimal(10),
            'USD_millions','sql',measurement_definition='sales_revenue')
        self.assertEqual(match_claim(claim,fact).relation,'INCONCLUSIVE')
        qualitative, _ = await self.single('Demand remains patchy.', {
            'metric':'demand','assertion_type':'level','qualitative_text':'patchy'})
        self.assertEqual(qualitative.proposition.assertion_type,'qualitative')
        self.assertIsNone(qualitative.proposition.value)
