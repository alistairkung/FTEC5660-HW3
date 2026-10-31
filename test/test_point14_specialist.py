import asyncio
from contextlib import contextmanager
import json
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from fisher_agent.point14.financial_evidence_extractor import FinancialEvidenceExtractor
from fisher_agent.point14.transparency_specialist import TransparencySpecialist
from test_point14_financial import financial_sql
from test_point14_verifier import claims, judgement, DATES

PERIODS = ('2025Q3','2025Q4','2026Q1','2026Q2')
VALUES = dict(zip(PERIODS, ('150', '100', '100', '90')))


@tool
def documents() -> str:
    """List synthetic calls."""
    return '\n'.join(f'earnings_call_{p.lower()}.md: Call {p}' for p in PERIODS)


@tool
def document(name: str) -> str:
    """Read a synthetic call."""
    period = next(p for p in PERIODS if p.lower() in name)
    return f'Date: {DATES[period]}\n\nCEO: Revenue was USD {VALUES[period]} thousand.'


def tools():
    return [documents.model_copy(update={'name': 'list_documents'}),
            document.model_copy(update={'name': 'read_document'}),
            financial_sql.model_copy(update={'name': 'sql_query'})]


def extraction():
    return {'claims':[{'document': c.document, 'period':c.period, 'topic':'revenue',
        'quotation':c.quotation, 'kind':'favourable', 'proposition':{
            'subject':'company', 'metric':'revenue', 'period':c.period, 'assertion_type':'level',
            'value_text':str(c.proposition.value), 'unit':'USD_thousands', 'basis':'level',
            'comparator_period':None, 'direction':None, 'qualifiers':[], 'certainty':'asserted',
            'measurement_definition':'sales_revenue', 'definition_quotation':'Revenue'}}
        for c in claims()]}


def model(*responses):
    instance = AsyncMock()
    instance.ainvoke.side_effect = [AIMessage(content=json.dumps(r), usage_metadata={
        'input_tokens':10, 'output_tokens':20, 'total_tokens':30}) for r in responses]
    return instance


class RecordingTracing:
    def __init__(self):
        self.stack = []
        self.events = []

    def config(self, **kwargs):
        return {'metadata':kwargs, 'callbacks':[]}

    @contextmanager
    def observation(self, name, **kwargs):
        from unittest.mock import Mock
        self.events.append((name, tuple(self.stack), kwargs))
        self.stack.append(name)
        try:
            yield Mock(trace_id='test-trace')
        finally:
            self.stack.pop()


class SpecialistTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.snapshot = await FinancialEvidenceExtractor().extract('synthetic', financial_sql)
        self.verification = judgement(self.snapshot, claims())

    async def test_end_to_end_preserves_independent_findings_and_explicit_uncertainty(self):
        tracing = RecordingTracing()
        specialist = TransparencySpecialist(model(extraction(), self.verification), tracing)
        result = await specialist.evaluate('synthetic', tools())
        self.assertIsNone(result.verdict)
        self.assertEqual(result.point_id, 14)
        self.assertEqual(result.status, 'insufficient_evidence')
        self.assertEqual(len(result.claims), 4)
        self.assertTrue(all(m.relation == 'SUPPORTED' for m in result.decision.matches))
        self.assertTrue(result.events)
        self.assertTrue(result.coverage.complete)
        self.assertEqual(result.diagnostics.usage['total_tokens'], 60)
        self.assertEqual(result.public_result()['points'], {14:'FAIL'})
        self.assertIn('fallback', result.public_result()['summary'])
        self.assertEqual(result.trace_id, 'test-trace')
        for name, parents, _ in tracing.events:
            if name != 'point14':
                self.assertIn('point14', parents)
        self.assertFalse(tracing.stack)

    async def test_complete_no_adverse_event_scope_can_pass_without_extra_model_judge(self):
        raw = financial_sql.invoke({'query':''})
        lines = raw.splitlines()
        for i in range(1, len(lines)):
            values = lines[i].split(' | '); values[1] = '100'; lines[i] = ' | '.join(values)
        supplied = tools()
        supplied[2] = AsyncMock(name='sql')
        supplied[2].name = 'sql_query'
        supplied[2].ainvoke.return_value = '\n'.join(lines)
        candidate = extraction()
        for item in candidate['claims']:
            item['quotation'] = 'Revenue was USD 100 thousand.'
            item['proposition']['value_text'] = '100'
        @tool
        def flat_document(name:str)->str:
            """Read a synthetic flat-performance call."""
            p = next(p for p in PERIODS if p.lower() in name)
            return f'Date: {DATES[p]}\n\nCEO: Revenue was USD 100 thousand.'
        supplied[1] = flat_document.model_copy(update={'name':'read_document'})
        verification = {**self.verification, 'disclosures':[]}
        instance = model(candidate, verification)
        result = await TransparencySpecialist(instance).evaluate('synthetic', supplied)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(result.assessment, 'TRANSPARENT')
        self.assertEqual(result.status, 'assessed')
        self.assertEqual(result.diagnostics.model_calls, 2)
        self.assertEqual(result.diagnostics.adjudications, 0)

    async def test_api_error_isolated_from_next_company_and_not_a_researched_fail(self):
        instance = model(extraction(), self.verification)
        original = list(instance.ainvoke.side_effect)
        instance.ainvoke.side_effect = [RuntimeError('secret must not be retained'), *original]
        specialist = TransparencySpecialist(instance)
        first = await specialist.evaluate('broken', tools())
        second = await specialist.evaluate('healthy', tools())
        self.assertIsNone(first.verdict)
        self.assertEqual(first.status, 'api_error')
        self.assertNotIn('secret', repr(first))
        self.assertEqual(second.status, 'insufficient_evidence')
        self.assertEqual(second.diagnostics.model_calls, 2)

    async def test_invalid_verification_repairs_once_without_adjudication_loop(self):
        result = await TransparencySpecialist(model(extraction(), {}, {})).evaluate('x', tools())
        self.assertIsNone(result.verdict)
        self.assertEqual(result.status, 'invalid_output')
        self.assertEqual(result.diagnostics.parsing_retries, 1)
        self.assertEqual(result.diagnostics.model_calls, 3)
        self.assertEqual(result.diagnostics.adjudications, 0)

    async def test_deadline(self):
        with patch('fisher_agent.point14.transparency_specialist.COMPANY_DEADLINE_SECONDS', 0):
            result = await TransparencySpecialist(model()).evaluate('slow', tools())
        self.assertIsNone(result.verdict)
        self.assertEqual(result.status, 'deadline')

    async def test_sql_failure_missing_document_and_cancellation(self):
        supplied = tools(); supplied[2] = AsyncMock(name='bad_sql'); supplied[2].name = 'sql_query'
        supplied[2].ainvoke.return_value = 'SQL error: missing data'
        result = await TransparencySpecialist(model()).evaluate('x', supplied)
        self.assertEqual(result.status, 'retrieval_error')
        self.assertEqual(result.error_stage, 'financial-extraction')
        supplied = tools(); supplied[0] = AsyncMock(); supplied[0].name = 'list_documents'
        supplied[0].ainvoke.return_value = 'annual_letter_2025.md: Letter'
        self.assertEqual((await TransparencySpecialist(model()).evaluate('x', supplied)).status, 'retrieval_error')
        instance = model(); instance.ainvoke.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await TransparencySpecialist(instance).evaluate('x', tools())

    async def test_native_callbacks_keep_usage_and_company_metadata(self):
        from test_langchain_tracing import RecordingCallback
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        from observability import Tracing
        handler = RecordingCallback()
        fake_model = FakeListChatModel(responses=[json.dumps(extraction()), json.dumps(self.verification)])
        with Tracing() as tracing:
            with patch.object(tracing, 'config', return_value={
                    'callbacks':[handler], 'metadata':{'company_id':'native', 'fisher_point':'14'}}):
                result = await TransparencySpecialist(fake_model, tracing).evaluate('native', tools())
        self.assertEqual(result.status, 'insufficient_evidence')
        for event, payload in handler.events:
            if event in ('model-start', 'tool-start'):
                self.assertEqual(payload['metadata']['company_id'], 'native')
        self.assertEqual(sum(event == 'tool-start' for event, _ in handler.events), 6)
        self.assertEqual(sum(event == 'model-start' for event, _ in handler.events), 2)
