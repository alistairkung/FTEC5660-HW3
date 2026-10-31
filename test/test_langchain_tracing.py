"""Real LangChain execution with a mocked Langfuse callback boundary."""

import asyncio
from contextlib import nullcontext
import os
import unittest
from unittest.mock import Mock, patch

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from observability import Tracing


class RecordingCallback(BaseCallbackHandler):
    def __init__(self):
        self.events = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.events.append(("model-start", kwargs))

    def on_llm_end(self, response, **kwargs):
        self.events.append(("model-end", response))

    def on_llm_error(self, error, **kwargs):
        self.events.append(("model-error", error))

    def on_tool_start(self, serialized, input_str, **kwargs):
        self.events.append(("tool-start", kwargs))

    def on_tool_end(self, output, **kwargs):
        self.events.append(("tool-end", output))

    def on_tool_error(self, error, **kwargs):
        self.events.append(("tool-error", error))


class FakeModel(BaseChatModel):
    fail: bool = False

    @property
    def _llm_type(self):
        return "mock-deepseek"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.fail:
            raise RuntimeError("mock model failure")
        message = AIMessage(content="TRACE_OK", usage_metadata={
            "input_tokens": 4, "output_tokens": 2, "total_tokens": 6,
        }, response_metadata={"model_name": "deepseek-v4-flash"})
        return ChatResult(generations=[ChatGeneration(message=message)])


@tool
def smoke_tool(fail: bool = False) -> str:
    """Return synthetic observability data, or raise a test error."""
    if fail:
        raise ValueError("mock tool failure")
    return "synthetic result"


class LangChainTracingTests(unittest.IsolatedAsyncioTestCase):
    async def test_callbacks_receive_model_usage_metadata_and_direct_tool_events(self):
        handler = RecordingCallback()
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": "secret"},
                        clear=True), patch("observability.tracing._load_backend", return_value=(
                            Mock(), Mock(return_value=handler), lambda **kwargs: nullcontext(),
                        )):
            with Tracing() as tracing:
                config = tracing.config(company_id="synthetic", fisher_point=7)
                response = await FakeModel().ainvoke("test", config=config)
                self.assertEqual(response.content, "TRACE_OK")
                self.assertEqual(smoke_tool.invoke({}, config=config), "synthetic result")
                with self.assertRaises(RuntimeError):
                    await FakeModel(fail=True).ainvoke("test", config=config)
                with self.assertRaises(ValueError):
                    smoke_tool.invoke({"fail": True}, config=config)
        events = dict(handler.events)
        self.assertEqual(events["model-start"]["metadata"]["company_id"], "synthetic")
        self.assertEqual(events["tool-start"]["metadata"]["fisher_point"], "7")
        generation = events["model-end"].generations[0][0].message
        self.assertEqual(generation.usage_metadata["total_tokens"], 6)
        self.assertEqual(generation.response_metadata["model_name"], "deepseek-v4-flash")
        self.assertIsInstance(events["model-error"], RuntimeError)
        self.assertIsInstance(events["tool-error"], ValueError)

    async def test_concurrent_company_configs_do_not_mix_metadata(self):
        handlers = []

        def new_handler(**kwargs):
            handler = RecordingCallback()
            handlers.append(handler)
            return handler

        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": "secret"},
                        clear=True), patch("observability.tracing._load_backend", return_value=(
                            Mock(), new_handler, lambda **kwargs: nullcontext(),
                        )):
            with Tracing() as tracing:
                await asyncio.gather(*(
                    FakeModel().ainvoke("test", config=tracing.config(company_id=name, fisher_point=point))
                    for name, point in (("a", 1), ("b", 7))
                ))
        actual = [next(payload["metadata"] for event, payload in handler.events if event == "model-start")
                  for handler in handlers]
        self.assertEqual([(m["company_id"], m["fisher_point"]) for m in actual], [("a", "1"), ("b", "7")])

    async def test_callback_failure_does_not_fail_model_call(self):
        handler = RecordingCallback()
        handler.on_chat_model_start = Mock(side_effect=RuntimeError("tracing down"))
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": "secret"},
                        clear=True), patch("observability.tracing._load_backend", return_value=(
                            Mock(), Mock(return_value=handler), lambda **kwargs: nullcontext(),
                        )):
            with Tracing() as tracing:
                response = await FakeModel().ainvoke("test", config=tracing.config())
        self.assertEqual(response.content, "TRACE_OK")
