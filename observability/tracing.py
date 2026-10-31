"""Best-effort Langfuse configuration for LangChain and explicit observations.

Initialize once after loading environment variables. Close only after all work has
finished: the SDK shares project resources between its clients and callbacks.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

LOGGER = logging.getLogger(__name__)
CURRENT_TRACING: ContextVar[Tracing | None] = ContextVar("hw3_tracing", default=None)


def current_tracing() -> Tracing | None:
    """Get the application-owned lifecycle, including inside async child tasks."""
    return CURRENT_TRACING.get()


class Span(Protocol):
    """The small part of an SDK observation used by this module."""

    trace_id: str

    def update(self, **kwargs: Any) -> Any: ...


class Client(Protocol):
    def start_as_current_observation(self, **kwargs: Any) -> AbstractContextManager[Span]: ...

    def flush(self) -> None: ...

    def shutdown(self) -> None: ...


def _load_backend() -> tuple[Client, Callable[..., Any], Callable[..., Any]]:
    # Deliberately lazy: no SDK imports, threads or requests when tracing is off.
    from langfuse import Langfuse, propagate_attributes
    from langfuse.langchain import CallbackHandler

    return Langfuse(), CallbackHandler, propagate_attributes


def _warn(stage: str) -> None:
    # Exception text may contain credentials, request headers or provider payloads.
    LOGGER.warning("Langfuse %s unavailable; continuing without that tracing operation", stage)


def _metadata(company_id: str | None, fisher_point: int | None) -> dict[str, str]:
    metadata = {"assignment": "ftec5660-hw3"}
    if company_id is not None:
        metadata["company_id"] = company_id
    if fisher_point is not None:
        metadata["fisher_point"] = str(fisher_point)
    return metadata


class Observation:
    """A no-op when disabled; SDK update failures never affect application work."""

    def __init__(self, span: Span | None = None) -> None:
        self._span = span

    @property
    def trace_id(self) -> str | None:
        try:
            return self._span.trace_id if self._span is not None else None
        except Exception:
            _warn("trace ID")
            return None

    def update(self, **kwargs: Any) -> None:
        if self._span is not None:
            try:
                self._span.update(**kwargs)
            except Exception:
                _warn("observation update")


class Tracing:
    """One application-owned tracing lifecycle; credentials are optional.

    Use a single instance for a batch. Reuse each returned LangChain config for
    the relevant company/point. Native callbacks capture model, usage, timings,
    tool events and errors; application code must still pass config explicitly.
    """

    def __init__(self) -> None:
        self._client: Client | None = None
        self._callback_factory: Callable[..., Any] | None = None
        self._propagate: Callable[..., Any] | None = None
        self._closed = False
        self._context_token: Token[Tracing | None] | None = None
        self._public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        enabled = os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower().strip()
        if enabled in {"false", "0", "no", "off"}:
            return
        if not self._public_key or not os.getenv("LANGFUSE_SECRET_KEY", "").strip():
            return
        try:
            self._client, self._callback_factory, self._propagate = _load_backend()
        except Exception:
            _warn("initialization")

    @property
    def enabled(self) -> bool:
        """Local initialization status, not proof of remote delivery."""
        return self._client is not None and not self._closed

    def config(
        self, *, company_id: str | None = None, fisher_point: int | None = None,
        run_name: str = "hw3-analysis",
    ) -> RunnableConfig:
        """Create reusable config; attach once at the outer LangChain invocation.

        A fresh handler keeps unrelated configs' run state separate. Descendant
        LangChain calls inherit callbacks. Do not attach this handler a second
        time to descendants that already inherit it.
        """
        config: RunnableConfig = {
            "run_name": run_name,
            "metadata": _metadata(company_id, fisher_point),
            "tags": ["ftec5660-hw3"],
            "callbacks": [],
        }
        if self.enabled and self._callback_factory is not None:
            try:
                handler = self._callback_factory(public_key=self._public_key)
                # LangChain catches callback exceptions when this flag is false.
                handler.raise_error = False
                config["callbacks"] = [handler]
            except Exception:
                _warn("callback configuration")
        return config

    @contextmanager
    def observation(
        self, name: str, *, company_id: str | None = None,
        fisher_point: int | None = None,
        as_type: Literal["span", "agent", "tool", "retriever"] = "span",
        input: Any = None,
    ) -> Iterator[Observation]:
        """Nest non-LangChain work without wrapping or modifying supplied tools.

        Use within async functions with ordinary `with`; context is task-local.
        Application exceptions and cancellation propagate unchanged. Do not send
        clients, configuration objects or credentials as observation input.
        """
        contexts: list[AbstractContextManager[Any]] = []
        observation = Observation()
        try:
            if self.enabled and self._client is not None and self._propagate is not None:
                metadata = _metadata(company_id, fisher_point)
                propagation = self._propagate(metadata=metadata, tags=["ftec5660-hw3"])
                propagation.__enter__()
                contexts.append(propagation)
                scope = self._client.start_as_current_observation(
                    name=name, as_type=as_type, input=input, metadata=metadata,
                )
                span = scope.__enter__()
                contexts.append(scope)
                observation = Observation(span)
        except Exception:
            _warn("observation start")
        try:
            yield observation
        except BaseException as error:
            observation.update(level="ERROR", status_message=type(error).__name__)
            raise
        finally:
            for context in reversed(contexts):
                try:
                    # Error status was recorded above without leaking exception text.
                    context.__exit__(None, None, None)
                except Exception:
                    _warn("observation end")

    def flush(self) -> None:
        """Best effort; remote acceptance must be checked separately in Langfuse."""
        if self.enabled and self._client is not None:
            try:
                self._client.flush()
            except Exception:
                _warn("flush")

    def close(self) -> None:
        """Flush, then shut down once, including when flush fails."""
        if self._closed:
            return
        self.flush()
        self._closed = True
        if self._client is not None:
            try:
                self._client.shutdown()
            except Exception:
                _warn("shutdown")

    def __enter__(self) -> Tracing:
        self._context_token = CURRENT_TRACING.set(self)
        return self

    def __exit__(self, *_: Any) -> None:
        try:
            self.close()
        finally:
            if self._context_token is not None:
                CURRENT_TRACING.reset(self._context_token)
                self._context_token = None
