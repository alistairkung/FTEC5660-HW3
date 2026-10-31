"""Run the specialist through real LangChain callbacks with a fake Langfuse backend."""
from contextlib import contextmanager, nullcontext
import os
import unittest
from unittest.mock import Mock, patch

from fisher_agent.evidence_interpreter import EvidenceInterpreter
from fisher_agent.sales_specialist import SalesSpecialist
from observability import Tracing
from test_langchain_tracing import RecordingCallback
from test_sales_specialist import ScriptedModel, decision, interviews


class SalesTracingTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_contains_point_metadata_tools_decisions_usage_and_fallback(self):
        observations = []
        handler = RecordingCallback()

        @contextmanager
        def scope(**kwargs):
            span = Mock(trace_id='offline-trace')
            observations.append((kwargs, span))
            yield span

        backend = Mock(start_as_current_observation=scope)
        model = ScriptedModel(responses=[decision('UNCERTAIN'), decision('UNCERTAIN'), decision()])
        tools, _ = interviews()
        with patch.dict(os.environ, {'LANGFUSE_PUBLIC_KEY': 'fake', 'LANGFUSE_SECRET_KEY': 'fake'},
                        clear=True), patch('observability.tracing._load_backend', return_value=(
                            backend, lambda **kwargs: handler, lambda **kwargs: nullcontext())):
            with Tracing() as tracing:
                result = await SalesSpecialist(EvidenceInterpreter(model), tracing).assess('synthetic', tools)
        names = [kwargs['name'] for kwargs, _ in observations]
        self.assertIn('assess-sales', names)
        self.assertIn('classify-sales-initial', names)
        self.assertIn('reassess-sales', names)
        self.assertIn('adjudicate-sales', names)
        self.assertEqual(result.trace_id, 'offline-trace')
        events = [event for event, _ in handler.events]
        self.assertEqual(events.count('tool-start'), 2)
        self.assertEqual(events.count('model-start'), 3)
        self.assertEqual(result.usage['total_tokens'], 90)
        for event, payload in handler.events:
            if event in ('model-start', 'tool-start'):
                self.assertEqual(payload['metadata']['company_id'], 'synthetic')
                self.assertEqual(payload['metadata']['fisher_point'], '4')
        final = observations[0][1].update.call_args.kwargs['output']
        self.assertEqual(final['points'], {4: 'PASS'})
        self.assertTrue(final['fallback_triggered'])
        backend.flush.assert_called_once()
        backend.shutdown.assert_called_once()

    async def test_unavailable_optional_backend_does_not_change_assessment(self):
        with patch.dict(os.environ, {'LANGFUSE_PUBLIC_KEY': 'fake', 'LANGFUSE_SECRET_KEY': 'fake'},
                        clear=True), patch('observability.tracing._load_backend', side_effect=ImportError):
            with Tracing() as tracing:
                tools, _ = interviews()
                result = await SalesSpecialist(EvidenceInterpreter(
                    ScriptedModel(responses=[decision()])), tracing).assess('synthetic', tools)
        self.assertEqual(result.verdict, 'PASS')
        self.assertEqual(result.status, 'assessed')
