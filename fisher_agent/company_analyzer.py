"""Bounded per-company integration of the three independently validated specialists."""
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
from .returns_disclosure import Point14ReturnsStrategy
from .returns_disclosure.records import ReturnsRun
from .sales_records import SalesResult
from .sales_specialist import SalesSpecialist

COMPANY_CONCURRENCY = 2
COMPANY_DEADLINE_SECONDS = 125
BATCH_DEADLINE_SECONDS = 1200


@dataclass
class CompanyAssessment:
    company_id: str
    points: dict[int, PointResult]
    sales: SalesResult | None = None
    margin: MarginResult | None = None
    trace_id: str | None = None
    duration_seconds: float = 0
    returns_run: ReturnsRun | None = None

    def public_result(self) -> dict:
        """Return exactly the chosen points, retaining unresolved state internally."""
        points, summaries = {}, []
        for number in (4, 5, 14):
            result = self.points.get(number) or _error(self.company_id, number, 'missing_result')
            points[number] = result.verdict or 'FAIL'
            if result.verdict is None:
                kind = 'insufficient-evidence' if result.status == 'insufficient_evidence' else 'operational'
                summaries.append(f'Point {number} {kind} FAIL fallback ({result.status}); '
                                 'no supported investment verdict.')
            summaries.append(result.summary)
        return {'points': points, 'summary': ' '.join(summaries)}


def _error(company_id: str, point: int, code: str, error_type: str | None = None) -> PointResult:
    return PointResult(company_id, point, None, 'error',
                       f'Point {point} processing failed ({code}); evidence is unresolved.',
                       diagnostics=(Diagnostic('company', code, error_type),))


def _validate_identity(result: PointResult, company_id: str, point: int) -> PointResult:
    if (not isinstance(result, PointResult) or result.company_id != company_id
            or result.point != point or result.status == 'pending'):
        raise ValueError('Specialist returned an invalid company, point or execution state')
    return result


def _trace_output(assessment: CompanyAssessment) -> dict:
    sales, margin, returns = assessment.sales, assessment.margin, assessment.returns_run
    usage = {key: sum(run.usage.get(key, 0) for run in (sales, returns) if run is not None)
             for key in ('input_tokens', 'output_tokens', 'total_tokens')}
    return {**assessment.public_result(),
            'point_statuses': {point: result.status for point, result in assessment.points.items()},
            'point_results': {point: asdict(result) for point, result in assessment.points.items()},
            'duration_seconds': assessment.duration_seconds,
            'model_calls': (sales.model_calls if sales else 0) + (returns.model_calls if returns else 0),
            'usage': usage,
            'usage_complete': sales is not None and returns is not None,
            'sales': {'status': sales.status, 'model_calls': sales.model_calls, 'usage': sales.usage,
                      'interviews_used': sales.interviews_used, 'diagnostics': sales.diagnostics,
                      'fallback_triggered': sales.fallback_triggered,
                      'adjudication_used': sales.adjudication_used} if sales else None,
            'margin': {'status': margin.status, 'sql_calls': len(margin.evidence),
                       'error': asdict(margin.error) if margin.error else None} if margin else None,
            'point14': {'status': returns.point_result.status, 'failure_status': returns.failure_status,
                        'model_calls': returns.model_calls, 'format_repairs': returns.format_repairs,
                        'usage': returns.usage, 'tool_calls': returns.tool_calls,
                        'diagnostics': [asdict(item) for item in returns.diagnostics],
                        'findings': [asdict(item) for item in returns.findings]} if returns else None}


class CompanyAnalyzer:
    def __init__(self, sales: SalesSpecialist, margin: MarginRunner | None = None, *,
                 returns_strategy: Point14ReturnsStrategy,
                 tracing: Tracing | None = None, concurrency: int = COMPANY_CONCURRENCY,
                 deadline_seconds: float = COMPANY_DEADLINE_SECONDS,
                 batch_deadline_seconds: float = BATCH_DEADLINE_SECONDS):
        if (not 1 <= concurrency <= COMPANY_CONCURRENCY or deadline_seconds <= 0
                or batch_deadline_seconds <= 0):
            raise ValueError('Use one or two company workers and a positive deadline')
        self._sales = sales
        self._margin = margin or MarginRunner(tracing=tracing)
        self._returns = returns_strategy
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
            return _validate_identity(adapt_sales(result), name, 4), result
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
                result = _validate_identity(adapt_margin(raw), name, 5)
                span.update(output=asdict(raw), level='DEFAULT' if result.verdict else 'ERROR')
                return result, raw
            except Exception as error:
                result = _error(name, 5, 'internal_error', type(error).__name__)
                span.update(output=asdict(result), level='ERROR')
                return result, None

    async def _returns_result(self, name: str, tools: list[BaseTool]) -> tuple[PointResult, ReturnsRun | None]:
        try:
            raw = await self._returns.assess(name, tools)
            return _validate_identity(raw.point_result, name, 14), raw
        except Exception as error:
            return _error(name, 14, 'internal_error', type(error).__name__), None

    async def _assess(self, name: str, tools: list[BaseTool], remaining: float) -> CompanyAssessment:
        started = monotonic()
        scope = (self._tracing.observation('assess-company', company_id=name,
                                          input={'implemented_points': [4, 5, 14]})
                 if self._tracing else nullcontext(Observation()))
        with scope as span:
            if remaining <= 0:
                assessment = CompanyAssessment(name, {
                    point: _error(name, point, 'batch_deadline') for point in (4, 5, 14)},
                    trace_id=span.trace_id, duration_seconds=round(monotonic() - started, 6))
                span.update(output=_trace_output(assessment), level='ERROR')
                return assessment
            sales = asyncio.create_task(self._sales_result(name, tools))
            margin = asyncio.create_task(self._margin_result(name, tools))
            returns = asyncio.create_task(self._returns_result(name, tools))
            tasks = {4: sales, 5: margin, 14: returns}
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
                sales=results[4][1], margin=results[5][1], returns_run=results[14][1],
                trace_id=span.trace_id, duration_seconds=round(monotonic() - started, 6))
            level = ('ERROR' if any(result.status == 'error' for result in assessment.points.values())
                     else 'WARNING' if any(result.verdict is None for result in assessment.points.values())
                     else 'DEFAULT')
            span.update(output=_trace_output(assessment), level=level)
            return assessment
