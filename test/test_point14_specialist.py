import asyncio
from contextlib import contextmanager
import json
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from fisher_agent.point14.transparency_specialist import TransparencySpecialist
from test_point14_financial import financial_sql
from test_point14_verifier import judgement

PERIODS = ('2025Q3','2025Q4','2026Q1','2026Q2')


@tool
def documents() -> str:
    """List synthetic calls."""
    return '\n'.join(f'earnings_call_{p.lower()}.md: Call {p}' for p in PERIODS)


@tool
def document(name: str) -> str:
    """Read a synthetic call."""
    return 'CEO: Revenue declined. We faced weaker demand and discussed the shortfall.'


def tools():
    return [documents.model_copy(update={'name': 'list_documents'}),
            document.model_copy(update={'name': 'read_document'}),
            financial_sql.model_copy(update={'name': 'sql_query'})]


def extraction():
    return {'claims':[{'document': f'earnings_call_{p.lower()}.md', 'period':p,
                      'topic':'revenue', 'quotation':'Revenue declined.',
                      'kind':'acknowledges_setback'} for p in PERIODS]}


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
    async def test_end_to_end_uses_supplied_tools_and_returns_point_only_provenance(self):
        tracing = RecordingTracing()
        specialist = TransparencySpecialist(model(extraction(), judgement()), tracing)
        result = await specialist.evaluate('synthetic', tools())
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(result.point_id, 14)
        self.assertEqual(result.status, 'assessed')
        self.assertEqual(len(result.claims), 4)
        self.assertEqual(result.diagnostics.usage['total_tokens'], 60)
        self.assertEqual(result.public_result()['points'], {14:'PASS'})
        self.assertIn('150.00 USD_thousands', result.reason)
        self.assertEqual(result.trace_id, 'test-trace')
        stages = {name for name, _, _ in tracing.events}
        self.assertTrue({'point14.financial-extraction', 'point14.document-retrieval',
                         'point14.claim-extraction', 'point14.quotation-validation',
                         'point14.transparency-verification', 'point14.final-verdict'} <= stages)
        for name, parents, _ in tracing.events:
            if name != 'point14':
                self.assertIn('point14', parents)
        self.assertFalse(tracing.stack)

    async def test_api_error_is_not_an_evidence_backed_fail_and_next_company_can_run(self):
        instance = model(extraction(), judgement())
        original = list(instance.ainvoke.side_effect)
        instance.ainvoke.side_effect = [RuntimeError('secret must not be retained'), *original]
        specialist = TransparencySpecialist(instance)
        first = await specialist.evaluate('broken', tools())
        second = await specialist.evaluate('healthy', tools())
        self.assertIsNone(first.verdict)
        self.assertEqual(first.status, 'api_error')
        self.assertIn('fallback', first.public_result()['summary'])
        self.assertNotIn('secret', repr(first))
        self.assertEqual(second.verdict, 'PASS')
        self.assertEqual(second.diagnostics.model_calls, 2)

    async def test_semantic_uncertainty_adjudicates_once_and_invalid_final_does_not_loop(self):
        uncertain = judgement('UNCERTAIN')
        instance = model(extraction(), uncertain, uncertain, uncertain)
        result = await TransparencySpecialist(instance).evaluate('x', tools())
        self.assertIsNone(result.verdict)
        self.assertEqual(result.status, 'invalid_output')
        self.assertEqual(result.diagnostics.adjudications, 1)
        self.assertEqual(result.diagnostics.parsing_retries, 1)
        self.assertEqual(result.diagnostics.model_calls, 4)

    async def test_successful_adjudication_and_deadline(self):
        result = await TransparencySpecialist(model(extraction(), judgement('UNCERTAIN'),
                                                    judgement())).evaluate('x', tools())
        self.assertEqual(result.status, 'adjudicated')
        self.assertEqual(result.verdict, 'PASS')
        with patch('fisher_agent.point14.transparency_specialist.COMPANY_DEADLINE_SECONDS', 0):
            result = await TransparencySpecialist(model()).evaluate('slow', tools())
        self.assertIsNone(result.verdict)
        self.assertEqual(result.status, 'deadline')

    async def test_sql_failure_missing_document_and_cancellation(self):
        supplied = tools()
        supplied[2] = AsyncMock(name='bad_sql')
        supplied[2].name = 'sql_query'
        supplied[2].ainvoke.return_value = 'SQL error: missing data'
        result = await TransparencySpecialist(model()).evaluate('x', supplied)
        self.assertEqual(result.status, 'retrieval_error')
        self.assertEqual(result.error_stage, 'financial-extraction')
        supplied = tools()
        supplied[0] = AsyncMock()
        supplied[0].name = 'list_documents'
        supplied[0].ainvoke.return_value = 'annual_letter_2025.md: Letter'
        result = await TransparencySpecialist(model()).evaluate('x', supplied)
        self.assertEqual(result.status, 'retrieval_error')
        instance = model()
        instance.ainvoke.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await TransparencySpecialist(instance).evaluate('x', tools())

    async def test_native_langchain_callbacks_keep_usage_and_company_metadata(self):
        from test_langchain_tracing import RecordingCallback
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        from observability import Tracing
        handler = RecordingCallback()
        fake_model = FakeListChatModel(responses=[json.dumps(extraction()), json.dumps(judgement())])
        with Tracing() as tracing:
            with patch.object(tracing, 'config', return_value={
                    'callbacks':[handler], 'metadata':{'company_id':'native', 'fisher_point':'14'}}):
                result = await TransparencySpecialist(fake_model, tracing).evaluate('native', tools())
        self.assertEqual(result.verdict, 'PASS')
        for event, payload in handler.events:
            if event in ('model-start', 'tool-start'):
                self.assertEqual(payload['metadata']['company_id'], 'native')
                self.assertEqual(payload['metadata']['fisher_point'], '14')
        self.assertEqual(sum(event == 'tool-start' for event, _ in handler.events), 6)
        self.assertEqual(sum(event == 'model-start' for event, _ in handler.events), 2)
