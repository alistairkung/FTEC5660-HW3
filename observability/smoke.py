"""Opt-in synthetic tracing smoke: one paid model call, no company analysis."""

from __future__ import annotations

import argparse
import asyncio
import os

import hw3
from observability import Tracing


async def smoke() -> str:
    """Require explicit consent/configuration before importing SDK or calling API."""
    hw3.load_env_file()
    if os.getenv("LANGFUSE_LIVE_SMOKE", "false").lower() != "true":
        raise RuntimeError("Set LANGFUSE_LIVE_SMOKE=true to allow one paid DeepSeek smoke call")
    if not all(os.getenv(key, "").strip() for key in (
        "DEEPSEEK_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL",
    )):
        raise RuntimeError("Smoke requires DeepSeek and Langfuse keys plus LANGFUSE_BASE_URL")

    from langchain_core.tools import tool
    from langchain_deepseek import ChatDeepSeek

    @tool
    def tracing_probe(fail: bool = False) -> str:
        """Emit synthetic tracing data; never read company evidence."""
        if fail:
            raise ValueError("Intentional observability smoke error")
        return "synthetic tool response"

    with Tracing() as tracing:
        if not tracing.enabled:
            raise RuntimeError("Tracing did not initialize; check SDK installation and configuration")
        config = tracing.config(company_id="observability-smoke", fisher_point=1,
                                run_name="smoke-model-and-tools")
        with tracing.observation("hw3-observability-smoke", company_id="observability-smoke",
                                 fisher_point=1, input={"purpose": "synthetic tracing check"}) as root:
            model = ChatDeepSeek(model=hw3.MODEL_NAME, timeout=30, max_retries=0, max_tokens=16)
            response = await model.ainvoke("Reply with TRACE_OK only.", config=config)
            if not response.usage_metadata or response.usage_metadata.get("total_tokens", 0) <= 0:
                raise RuntimeError("DeepSeek did not return token usage metadata")
            tracing_probe.invoke({}, config=config)
            try:
                tracing_probe.invoke({"fail": True}, config=config)
            except ValueError:
                pass  # Expected: verify this child is ERROR in Langfuse.
            # Manual instrumentation is only for calls without native callbacks.
            with tracing.observation("smoke-explicit-tool", as_type="tool") as tool_observation:
                tool_observation.update(output="synthetic direct-call result")
            root.update(output={"smoke": "completed", "expected_tool_errors": 1})
            trace_id = root.trace_id
    if not trace_id:
        raise RuntimeError("No trace ID was recorded")
    return trace_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True,
                        help="allow one paid DeepSeek call (also requires LANGFUSE_LIVE_SMOKE=true)")
    parser.parse_args()
    print("Smoke trace ID:", asyncio.run(smoke()))
    print("Export attempted; verify remote delivery and contents using the README checklist.")


if __name__ == "__main__":
    main()
