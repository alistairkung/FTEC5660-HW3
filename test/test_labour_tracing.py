"""Native model/tool callback propagation through the existing optional lifecycle."""
from contextlib import contextmanager, nullcontext
import os
import unittest
from unittest.mock import Mock, patch

from fisher_agent.labour_specialist import LabourSpecialist
from observability import Tracing
from test_langchain_tracing import RecordingCallback
from test_labour_specialist import LabourModel, decision, interviews, UNCLEAR


class LabourTracingTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_tools_metadata_usage_and_results_reach_callbacks(self):
        observations = []
        handler = RecordingCallback()

        @contextmanager
        def scope(**kwargs):
            span = Mock(trace_id='offline-labour')
            observations.append((kwargs, span))
            yield span

        backend = Mock(start_as_current_observation=scope)
        model = LabourModel(responses=[decision('UNCERTAIN', UNCLEAR),
                                      decision(source='former_employee:working_conditions')])
        tools, _ = interviews(current=UNCLEAR)
        with patch.dict(os.environ, {'LANGFUSE_PUBLIC_KEY': 'fake', 'LANGFUSE_SECRET_KEY': 'fake'},
                        clear=True), patch('observability.tracing._load_backend', return_value=(
                            backend, lambda **kwargs: handler, lambda **kwargs: nullcontext())):
            with Tracing() as tracing:
                run = await LabourSpecialist(model, tracing).assess('synthetic', tools)
        self.assertEqual(run.trace_id, 'offline-labour')
        events = [event for event, _ in handler.events]
        self.assertEqual(events.count('tool-start'), 2)
        self.assertEqual(events.count('model-start'), 2)
        for event, payload in handler.events:
            if event in ('model-start', 'tool-start'):
                self.assertEqual(payload['metadata']['company_id'], 'synthetic')
                self.assertEqual(payload['metadata']['fisher_point'], '7')
        final = observations[0][1].update.call_args.kwargs['output']
        self.assertEqual((final['point'], final['verdict'], final['status']), (7, 'PASS', 'complete'))
        self.assertEqual(final['usage']['total_tokens'], 60)
        backend.flush.assert_called_once()
        backend.shutdown.assert_called_once()

    async def test_missing_credentials_or_unavailable_sdk_preserves_verdict(self):
        for env in ({}, {'LANGFUSE_PUBLIC_KEY': 'fake', 'LANGFUSE_SECRET_KEY': 'fake'}):
            with patch.dict(os.environ, env, clear=True), patch(
                    'observability.tracing._load_backend', side_effect=ImportError):
                with Tracing() as tracing:
                    tools, _ = interviews()
                    run = await LabourSpecialist(LabourModel(responses=[decision()]), tracing).assess(
                        'synthetic', tools)
                    self.assertEqual(run.point_result.verdict, 'PASS')
