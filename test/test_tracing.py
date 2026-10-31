"""Offline tracing contract tests: no SDK, credentials or network required."""

import asyncio
from contextlib import nullcontext
import os
import unittest
from unittest.mock import Mock, patch

from observability import Tracing, current_tracing


CREDENTIALS = {"LANGFUSE_PUBLIC_KEY": "test-public", "LANGFUSE_SECRET_KEY": "test-secret"}


class TracingTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, CREDENTIALS, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = Mock()
        self.span = Mock(trace_id="a" * 32)
        self.scope = Mock()
        self.scope.__enter__ = Mock(return_value=self.span)
        self.scope.__exit__ = Mock(return_value=False)
        self.client.start_as_current_observation.return_value = self.scope
        self.handler = Mock()
        self.factory = Mock(return_value=self.handler)
        self.propagate = Mock(side_effect=lambda **kwargs: nullcontext())
        self.loader = patch("observability.tracing._load_backend", return_value=(
            self.client, self.factory, self.propagate,
        )).start()
        self.addCleanup(patch.stopall)

    def test_deepseek_only_or_partial_credentials_never_load_sdk(self):
        for environment in ({"DEEPSEEK_API_KEY": "not-exported"},
                            {"LANGFUSE_PUBLIC_KEY": "test"},
                            {"LANGFUSE_SECRET_KEY": "test"}):
            with self.subTest(environment=list(environment)), patch.dict(os.environ, environment, clear=True):
                with Tracing() as tracing:
                    self.assertFalse(tracing.enabled)
                    self.assertEqual(tracing.config()["callbacks"], [])
                    with tracing.observation("disabled") as observation:
                        observation.update(output="still works")
                        self.assertIsNone(observation.trace_id)
        self.loader.assert_not_called()

    def test_explicit_disable_never_loads_sdk(self):
        for value in ("false", "FALSE", "0", "no", "off"):
            with patch.dict(os.environ, {"LANGFUSE_TRACING_ENABLED": value}):
                self.assertFalse(Tracing().enabled)
        self.loader.assert_not_called()

    def test_missing_sdk_or_invalid_configuration_is_nonfatal_and_sanitized(self):
        for error in (ImportError("not installed"), ValueError("test-secret")):
            self.loader.side_effect = error
            with self.assertLogs("observability.tracing", level="WARNING") as captured:
                with Tracing() as tracing:
                    self.assertFalse(tracing.enabled)
            self.assertNotIn("test-secret", " ".join(captured.output))

    def test_configs_have_independent_metadata_and_non_raising_callbacks(self):
        tracing = Tracing()
        first = tracing.config(company_id="company-a", fisher_point=7, run_name="interpret-interview")
        second = tracing.config(company_id="company-b", fisher_point=1)
        first["metadata"]["company_id"] = "changed"
        self.assertEqual(second["metadata"], {
            "assignment": "ftec5660-hw3", "company_id": "company-b", "fisher_point": "1",
        })
        self.assertEqual(first["run_name"], "interpret-interview")
        self.assertEqual(first["callbacks"], [self.handler])
        self.assertFalse(self.handler.raise_error)
        self.factory.assert_called_with(public_key="test-public")

    def test_callback_factory_failure_preserves_usable_config(self):
        self.factory.side_effect = RuntimeError("unavailable")
        self.assertEqual(Tracing().config(company_id="a")["callbacks"], [])

    def test_explicit_tool_observation_propagates_metadata_and_output(self):
        with Tracing() as tracing:
            with tracing.observation("read_document", company_id="a", fisher_point=14,
                                     as_type="tool", input={"name": "call.md"}) as observation:
                observation.update(output="tool response")
                self.assertEqual(observation.trace_id, "a" * 32)
        self.client.start_as_current_observation.assert_called_once_with(
            name="read_document", as_type="tool", input={"name": "call.md"},
            metadata={"assignment": "ftec5660-hw3", "company_id": "a", "fisher_point": "14"},
        )
        self.assertEqual(self.propagate.call_args.kwargs["metadata"]["company_id"], "a")
        self.span.update.assert_called_once_with(output="tool response")
        self.scope.__exit__.assert_called_once()

    def test_application_exception_is_never_swallowed_or_replaced_by_cleanup(self):
        original = ValueError("application failed")
        self.scope.__exit__.side_effect = RuntimeError("export failed")
        self.client.flush.side_effect = RuntimeError("flush failed")
        self.client.shutdown.side_effect = RuntimeError("shutdown failed")
        with self.assertRaises(ValueError) as caught:
            with Tracing() as tracing:
                with tracing.observation("failing"):
                    raise original
        self.assertIs(caught.exception, original)
        self.span.update.assert_called_once_with(level="ERROR", status_message="ValueError")
        self.client.shutdown.assert_called_once()

    def test_cancellation_propagates_and_observation_closes(self):
        with self.assertRaises(asyncio.CancelledError):
            with Tracing() as tracing:
                with tracing.observation("cancelled"):
                    raise asyncio.CancelledError()
        self.scope.__exit__.assert_called_once()
        self.client.shutdown.assert_called_once()

    def test_observation_start_and_update_failures_do_not_repeat_work(self):
        for failure in ("start", "enter", "update"):
            with self.subTest(failure=failure):
                self.client.start_as_current_observation.side_effect = (
                    RuntimeError("start") if failure == "start" else None)
                self.scope.__enter__.side_effect = RuntimeError("enter") if failure == "enter" else None
                self.span.update.side_effect = RuntimeError("update") if failure == "update" else None
                calls = []
                with Tracing() as tracing:
                    with tracing.observation("best-effort") as observation:
                        calls.append("work")
                        observation.update(output="result")
                self.assertEqual(calls, ["work"])

    def test_close_flushes_then_shuts_down_once_and_disables_callbacks(self):
        tracing = Tracing()
        tracing.close()
        tracing.close()
        tracing.flush()
        self.assertEqual([call[0] for call in self.client.method_calls], ["flush", "shutdown"])
        self.assertFalse(tracing.enabled)
        self.assertEqual(tracing.config()["callbacks"], [])

    def test_scoped_lifecycle_is_available_for_dependency_injection(self):
        self.assertIsNone(current_tracing())
        with Tracing() as tracing:
            self.assertIs(current_tracing(), tracing)
        self.assertIsNone(current_tracing())


class RunnerTests(unittest.TestCase):
    def test_wrapper_preserves_runner_result_and_closes_on_failure(self):
        from observability import run

        for failure in (False, True):
            with self.subTest(failure=failure), patch.object(run.hw3, "load_env_file") as load_env, \
                    patch.object(run.hw3, "main", side_effect=RuntimeError("runner") if failure else None,
                                 return_value=0) as runner, patch.object(run, "Tracing") as factory:
                if failure:
                    factory.return_value.__exit__.return_value = False
                    factory.return_value.__enter__.return_value.observation.return_value.__exit__.return_value = False
                    with self.assertRaises(RuntimeError):
                        run.main()
                else:
                    self.assertEqual(run.main(), 0)
                load_env.assert_called_once()
                runner.assert_called_once_with()
                factory.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
