"""Bound the synchronous margin strategy without blocking the asyncio batch."""
import asyncio
from contextvars import copy_context
import threading

from observability import Tracing

from .industry_margin_strategy import IndustryMarginStrategy
from .margin_records import MarginResult, MarginStrategy, SQLTool, StrategyError

SQL_DEADLINE_SECONDS = 10
SQL_CONCURRENCY = 2


class MarginRunner:
    """At most two physical workers, including calls whose awaiter timed out.

    Python cannot terminate a blocked tool thread. A timed-out worker retains
    its slot until it actually returns; queued companies also have deadlines.
    Daemon workers cannot hold interpreter shutdown hostage. Cancellation stops
    waiting and prevents the strategy from starting a subsequent SQL call.
    """

    def __init__(self, strategy: MarginStrategy | None = None, *,
                 timeout_seconds: float = SQL_DEADLINE_SECONDS,
                 tracing: Tracing | None = None):
        if timeout_seconds <= 0:
            raise ValueError('SQL deadline must be positive')
        self._strategy = strategy or IndustryMarginStrategy()
        self._timeout = timeout_seconds
        self._tracing = tracing
        self._slots = asyncio.Semaphore(SQL_CONCURRENCY)

    async def assess(self, company_id: str, sql_query: SQLTool) -> MarginResult:
        cancelled = threading.Event()

        async def run() -> MarginResult:
            await self._slots.acquire()
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            tracing = self._tracing

            class ScopedSQL:
                def invoke(self, input: dict[str, str]) -> str:
                    if cancelled.is_set():
                        raise TimeoutError('SQL deadline elapsed')
                    if tracing is None:
                        result = sql_query.invoke(input)
                    else:
                        result = sql_query.invoke(input, config=tracing.config(
                            company_id=company_id, fisher_point=5, run_name='margin-sql'))
                    if cancelled.is_set():
                        raise TimeoutError('SQL deadline elapsed')
                    return result

            def finish(result: MarginResult) -> None:
                self._slots.release()
                if not future.done():
                    future.set_result(result)

            def work() -> None:
                try:
                    result = self._strategy.evaluate(company_id, ScopedSQL())
                except Exception as error:
                    # Provider/tool exception messages may contain credentials.
                    result = self._error(company_id, 'internal_error', type(error).__name__)
                try:
                    loop.call_soon_threadsafe(finish, result)
                except RuntimeError:
                    pass  # The cancelled run's event loop has already closed.

            context = copy_context()
            worker = threading.Thread(target=context.run, args=(work,), daemon=True,
                                      name='hw3-margin')
            try:
                worker.start()
            except Exception:
                self._slots.release()
                raise
            return await future

        try:
            return await asyncio.wait_for(run(), self._timeout)
        except TimeoutError:
            return self._error(company_id, 'deadline', 'SQL processing deadline exceeded')
        finally:
            cancelled.set()

    def _error(self, company_id: str, code: str, message: str) -> MarginResult:
        return MarginResult(company_id, self._strategy.name, 'error', None, message,
                            error=StrategyError(code, message))
