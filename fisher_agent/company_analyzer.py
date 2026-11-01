"""Two-specialist milestone; Point 14 is explicitly pending, never fabricated."""
import asyncio
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from time import monotonic

from langchain_core.tools import BaseTool

from observability import Tracing
from observability.tracing import Observation

from .contracts import Diagnostic, PointResult
from .margin_records import MarginResult
from .margin_runner import MarginRunner
from .point_adapters import adapt_margin, adapt_sales
from .sales_records import SalesResult
from .sales_specialist import SalesSpecialist

COMPANY_CONCURRENCY = 2
COMPANY_DEADLINE_SECONDS = 95
BATCH_DEADLINE_SECONDS = 1200


@dataclass
class CompanyAssessment:
    company_id: str
    points: dict[int, PointResult]
    sales: SalesResult | None = None
    margin: MarginResult | None = None
    trace_id: str | None = None
    duration_seconds: float = 0

    def public_result(self) -> dict:
        """Only unresolved implemented points use the explicit public FAIL policy.

        The lecturer has no UNKNOWN. Internal None is retained for evaluation;
        missing Point 14 remains missing because its implementation is pending.
        """
        points, summaries = {}, []
        for number, result in self.points.items():
            if result.status != 'pending':
                points[number] = result.verdict or 'FAIL'
                if result.verdict is None:
                    summaries.append(f'Point {number} operational FAIL fallback ({result.status}); '
                                     'no supported investment verdict.')
            summaries.append(result.summary)
        return {'points': points, 'summary': ' '.join(summaries)}


def _error(company_id: str, point: int, code: str, error_type: str | None = None) -> PointResult:
    return PointResult(company_id, point, None, 'error',
                       f'Point {point} processing failed ({code}); evidence is unresolved.',
                       diagnostics=(Diagnostic('company', code, error_type),))


def _pending(company_id: str) -> PointResult:
    return PointResult(company_id, 14, None, 'pending',
                       'Point 14 pending; this is not a complete submission.')


class CompanyAnalyzer:
    def __init__(self, sales: SalesSpecialist, margin: MarginRunner | None = None, *,
                 tracing: Tracing | None = None, concurrency: int = COMPANY_CONCURRENCY,
                 deadline_seconds: float = COMPANY_DEADLINE_SECONDS,
                 batch_deadline_seconds: float = BATCH_DEADLINE_SECONDS):
        if (not 1 <= concurrency <= COMPANY_CONCURRENCY or deadline_seconds <= 0
                or batch_deadline_seconds <= 0):
            raise ValueError('Use one or two company workers and a positive deadline')
        self._sales = sales
        self._margin = margin or MarginRunner(tracing=tracing)
        self._tracing = tracing
        self._concurrency = concurrency
        self._deadline = deadline_seconds
        self._batch_deadline = batch_deadline_seconds

    async def assess_companies(self, companies: dict[str, list[BaseTool]]) -> dict[str, CompanyAssessment]:
        semaphore = asyncio.Semaphore(self._concurrency)
        batch_end = monotonic() + self._batch_deadline

        async def run(name: str, tools: list[BaseTool]) -> tuple[str, CompanyAssessment]:
            async with semaphore:
                remaining = min(self._deadline, batch_end - monotonic())
                return name, await self._assess(name, tools, remaining)

        return dict(await asyncio.gather(*(run(name, tools) for name, tools in companies.items())))

    async def analyze_companies(self, companies: dict[str, list[BaseTool]]) -> dict[str, dict]:
        return {name: result.public_result()
                for name, result in (await self.assess_companies(companies)).items()}

    async def _sales_result(self, name: str, tools: list[BaseTool]) -> tuple[PointResult, SalesResult | None]:
        try:
            result = await self._sales.assess(name, tools)
            return adapt_sales(result), result
        except Exception as error:
            return _error(name, 4, 'internal_error', type(error).__name__), None

    async def _margin_result(self, name: str, tools: list[BaseTool]) -> tuple[PointResult, MarginResult | None]:
        scope = (self._tracing.observation('assess-industry-margin', company_id=name, fisher_point=5)
                 if self._tracing else nullcontext(Observation()))
        with scope as span:
            try:
                sql = [tool for tool in tools if tool.name == 'sql_query']
                if len(sql) != 1:
                    raise ValueError('Exactly one company SQL tool is required')
                raw = await self._margin.assess(name, sql[0])
                result = adapt_margin(raw)
                span.update(output=asdict(raw), level='DEFAULT' if result.verdict else 'ERROR')
                return result, raw
            except Exception as error:
                result = _error(name, 5, 'internal_error', type(error).__name__)
                span.update(output=asdict(result), level='ERROR')
                return result, None

    async def _assess(self, name: str, tools: list[BaseTool], remaining: float) -> CompanyAssessment:
        started = monotonic()
        scope = (self._tracing.observation('assess-company', company_id=name,
                                          input={'implemented_points': [4, 5], 'pending_points': [14]})
                 if self._tracing else nullcontext(Observation()))
        with scope as span:
            if remaining <= 0:
                assessment = CompanyAssessment(name, {
                    4: _error(name, 4, 'batch_deadline'), 5: _error(name, 5, 'batch_deadline'),
                    14: _pending(name)}, trace_id=span.trace_id)
                span.update(output=assessment.public_result(), level='ERROR')
                return assessment
            sales = asyncio.create_task(self._sales_result(name, tools))
            margin = asyncio.create_task(self._margin_result(name, tools))
            tasks = {4: sales, 5: margin}
            try:
                _, pending = await asyncio.wait(tasks.values(), timeout=remaining)
            finally:
                for task in tasks.values():
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks.values(), return_exceptions=True)
            results = {point: (_error(name, point, 'deadline'), None) if task in pending
                       else task.result() for point, task in tasks.items()}
            assessment = CompanyAssessment(
                name, {point: pair[0] for point, pair in results.items()},
                results[4][1], results[5][1], span.trace_id, round(monotonic() - started, 6))
            assessment.points[14] = _pending(name)
            span.update(output={**assessment.public_result(),
                                'point_statuses': {p: r.status for p, r in assessment.points.items()},
                                'duration_seconds': assessment.duration_seconds})
            return assessment
