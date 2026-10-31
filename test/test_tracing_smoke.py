"""Live smoke is opt-in; default discovery remains entirely offline."""

import os
import unittest
from unittest.mock import patch

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


@unittest.skipUnless(os.getenv("LANGFUSE_LIVE_SMOKE", "false").lower() == "true",
                     "set LANGFUSE_LIVE_SMOKE=true to make one paid DeepSeek call")
class LiveSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_model_tools_and_usage(self):
        trace_id = await smoke()
        self.assertRegex(trace_id, r"^[0-9a-f]{32}$")
        print("Live smoke trace ID:", trace_id)
