"""Live smoke is opt-in; default discovery remains entirely offline."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from observability.smoke import smoke


class SmokeGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_live_calls_without_explicit_opt_in(self):
        with patch("observability.smoke.hw3.load_env_file"), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "LANGFUSE_LIVE_SMOKE=true"):
                await smoke()

    async def test_missing_credentials_prevent_live_calls(self):
        with patch("observability.smoke.hw3.load_env_file"), patch.dict(
            os.environ, {"LANGFUSE_LIVE_SMOKE": "true"}, clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires DeepSeek and Langfuse"):
                await smoke()

    async def test_smoke_model_explicitly_disables_thinking(self):
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(
            content='TRACE_OK', usage_metadata={'input_tokens': 2, 'output_tokens': 2, 'total_tokens': 4}))
        tracing = MagicMock()
        tracing.__enter__.return_value = tracing
        tracing.enabled = True
        tracing.config.return_value = {}
        tracing.observation.return_value.__enter__.return_value.trace_id = 'a' * 32
        environment = {'LANGFUSE_LIVE_SMOKE': 'true', 'DEEPSEEK_API_KEY': 'synthetic',
                       'LANGFUSE_PUBLIC_KEY': 'synthetic', 'LANGFUSE_SECRET_KEY': 'synthetic',
                       'LANGFUSE_BASE_URL': 'https://example.invalid'}
        with patch('observability.smoke.hw3.load_env_file'), patch.dict(os.environ, environment, clear=True), \
                patch('observability.smoke.Tracing', return_value=tracing), \
                patch('langchain_deepseek.ChatDeepSeek', return_value=model) as constructor:
            await smoke()
        self.assertEqual(constructor.call_args.kwargs['extra_body'],
                         {'thinking': {'type': 'disabled'}})


@unittest.skipUnless(os.getenv("LANGFUSE_LIVE_SMOKE", "false").lower() == "true",
                     "set LANGFUSE_LIVE_SMOKE=true to make one paid DeepSeek call")
class LiveSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_model_tools_and_usage(self):
        trace_id = await smoke()
        self.assertRegex(trace_id, r"^[0-9a-f]{32}$")
        print("Live smoke trace ID:", trace_id)
