import unittest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

from fisher_agent.point14.management_claim_extractor import ManagementClaimExtractor, source_quotation
from fisher_agent.point14.model_gateway import ModelGateway
from fisher_agent.point14.records import Diagnostics, Source, Transcript


class ClaimTests(unittest.IsolatedAsyncioTestCase):
    def transcript(self):
        return Transcript('2025Q3', 'earnings_call_2025q3.md', Source(
            'doc:2025Q3', 'x', 'read_document', {'name': 'earnings_call_2025q3.md'},
            'CEO: Revenue declined.\nWe faced weaker demand, and explained the shortfall.'))

    def proposal(self, **changes):
        claim = {'document': 'earnings_call_2025q3.md', 'period': '2025Q3',
                 'topic': 'revenue', 'quotation': 'Revenue declined.',
                 'kind': 'acknowledges_setback'}
        claim.update(changes)
        return {'claims': [claim]}

    async def extract(self, responses):
        import json
        model = AsyncMock()
        model.ainvoke.side_effect = [AIMessage(content=json.dumps(item)) for item in responses]
        diagnostics = Diagnostics()
        gateway = ModelGateway(model, diagnostics)
        claims = await ManagementClaimExtractor(gateway).extract((self.transcript(),))
        return claims, diagnostics, model

    async def test_extracts_source_grounded_claims_without_judgement(self):
        claims, diagnostics, model = await self.extract([self.proposal()])
        self.assertEqual(claims[0].quotation, 'Revenue declined.')
        self.assertEqual(claims[0].period, '2025Q3')
        self.assertEqual(claims[0].evidence_id, 'claim:2025Q3:1')
        self.assertEqual(diagnostics.model_calls, 1)
        self.assertNotIn('verdict', claims[0].__dict__)

    async def test_rejects_invented_quote_and_recovers_once(self):
        claims, diagnostics, model = await self.extract([
            self.proposal(quotation='Revenue rose 90%.'), self.proposal()])
        self.assertEqual(claims[0].quotation, 'Revenue declined.')
        self.assertEqual(diagnostics.quotation_rejections, 1)
        self.assertEqual(model.ainvoke.call_count, 2)

    async def test_rejects_misattributed_period_document_and_extra_facts(self):
        for proposal in [self.proposal(period='2025Q4'), self.proposal(document='unrelated.md'),
                         self.proposal(statement='We invented a new product'),
                         self.proposal(quotation='Revenue rose 90%.')]:
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                await self.extract([proposal, proposal])

    async def test_normalizes_only_whitespace_and_keeps_source_wording(self):
        claims, _, _ = await self.extract([self.proposal(
            quotation='Revenue declined.  We faced weaker demand, and explained the shortfall.')])
        self.assertEqual(claims[0].quotation,
                         'Revenue declined.\nWe faced weaker demand, and explained the shortfall.')

    async def test_rejects_an_analyst_question_as_a_management_claim(self):
        import json
        transcript = self.transcript()
        transcript = Transcript(transcript.period, transcript.name, Source(
            'doc:2025Q3', 'x', 'read_document', {'name':transcript.name},
            'Analyst: Did revenue decline?\n\nCEO: We will discuss the result.'))
        fake = AsyncMock()
        fake.ainvoke.return_value = AIMessage(content=json.dumps(self.proposal(quotation='Did revenue decline?')))
        with self.assertRaises(ValueError):
            await ManagementClaimExtractor(ModelGateway(fake, Diagnostics())).extract((transcript,))

    async def test_rejects_whitespace_only_quotation_in_extraction(self):
        with self.assertRaises(ValueError):
            await self.extract([self.proposal(quotation='        ')] * 2)

    def test_quotation_must_belong_wholly_to_one_management_turn(self):
        transcript = ('# Earnings call\n\nDate: 2026-01-01\n\n'
                      'Alex Ng (Chief Executive): Revenue declined.\nWe explained the shortfall.\n\n'
                      'Analyst: Why did demand fall?\n'
                      'Alex Ng: We discussed customer losses.\n\n'
                      'Morgan Lee (Chief Financial Officer): Costs rose.')
        for quotation in ('# Earnings call', 'Date: 2026-01-01',
                          'Revenue declined.\nWe explained the shortfall.\n\nAnalyst: Why did demand fall?',
                          'Why did demand fall?',
                          'We discussed customer losses.\n\nMorgan Lee (Chief Financial Officer): Costs rose.'):
            with self.subTest(quotation=quotation):
                self.assertIsNone(source_quotation(quotation, transcript))
        for quotation in ('Revenue declined.', 'We explained the shortfall.',
                          'We discussed customer losses.', 'Costs rose.',
                          'Alex Ng (Chief Executive): Revenue declined.'):
            with self.subTest(quotation=quotation):
                self.assertEqual(source_quotation(quotation, transcript), quotation)

    def test_untitled_unknown_speaker_is_not_management_evidence(self):
        self.assertIsNone(source_quotation('Revenue declined.', 'Unknown Person: Revenue declined.'))

    def test_executive_title_in_heading_does_not_establish_management_speech(self):
        self.assertIsNone(source_quotation('Revenue declined.',
                                           '# Alex Ng (Chief Executive): Revenue declined.'))

    def test_heading_after_management_turn_ends_speech_provenance(self):
        transcript = ('CEO: Revenue declined.\n\n# Subheading\n\nUnattributed text.\n\n'
                      'CFO: We explained higher costs.')
        for quotation in ('# Subheading', 'Subheading', 'Unattributed text.',
                          'Revenue declined.\n\n# Subheading'):
            with self.subTest(quotation=quotation):
                self.assertIsNone(source_quotation(quotation, transcript))
        for quotation in ('Revenue declined.', 'We explained higher costs.'):
            self.assertEqual(source_quotation(quotation, transcript), quotation)
