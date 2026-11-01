"""Bounded Point 7 workflow over company-scoped lecturer interview tools."""
import asyncio
from contextlib import nullcontext
from dataclasses import asdict
from time import monotonic
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from observability import Tracing
from observability.tracing import Observation

from .contracts import Diagnostic, PointResult, ProvenanceReference
from .labour_interpreter import LabourInterpreter, PROMPT_VERSION
from .labour_records import LabourAssessment, LabourEvidence, LabourRun
from .result_validator import InvalidAssessment

MODEL_TIMEOUT_SECONDS = 20
TOOL_TIMEOUT_SECONDS = 5
COMPANY_DEADLINE_SECONDS = 90
COMPANY_CONCURRENCY = 2
BATCH_DEADLINE_SECONDS = 1200
PARSING_RETRIES = 1


class LabourFailure(ValueError):
    """An already diagnosed operational failure; never an investment FAIL."""


class LabourSpecialist:
    def __init__(self, model: BaseChatModel, tracing: Tracing | None = None):
        self._interpreter = LabourInterpreter(model)
        self._tracing = tracing

    def _observation(self, name: str, company_id: str, **kwargs):
        if self._tracing is None:
            return nullcontext(Observation())
        return self._tracing.observation(name, company_id=company_id, fisher_point=7, **kwargs)

    def _config(self, company_id: str, stage: str) -> RunnableConfig:
        config = self._tracing.config(company_id=company_id, fisher_point=7, run_name=stage) \
            if self._tracing else {}
        config.setdefault('metadata', {}).update(company_id=company_id, fisher_point='7',
                                                 prompt_version=PROMPT_VERSION, stage=stage)
        return config

    def _set_result(self, run: LabourRun, status: Literal['complete', 'insufficient_evidence'], summary: str,
                    finding: LabourAssessment | None = None) -> None:
        run.point_result = PointResult(
            run.point_result.company_id, 7, finding.verdict if finding else None,
            status, summary,
            tuple(ProvenanceReference(e.evidence_id, e.company_id, e.source_tool) for e in run.evidence),
            run.point_result.diagnostics)

    def _diagnose(self, run: LabourRun, stage: str, code: str, error_type: str) -> None:
        # Provider exception strings may contain secrets. Retain only their type.
        diagnostic = Diagnostic(stage, code, error_type)
        previous = run.point_result
        run.point_result = PointResult(previous.company_id, 7, None, 'error',
            f'Point 7 unresolved ({code}); no supported investment verdict.',
            tuple(ProvenanceReference(e.evidence_id, e.company_id, e.source_tool) for e in run.evidence),
            previous.diagnostics + (diagnostic,))
        with self._observation('record-labour-diagnostic', previous.company_id,
                               input=asdict(diagnostic)) as span:
            span.update(output=asdict(diagnostic),
                        level='WARNING' if code == 'insufficient_evidence' else 'ERROR')

    async def assess(self, company_id: str, tools: list[BaseTool], *,
                     deadline_seconds: float | None = None) -> LabourRun:
        """Return a shared PointResult plus provenance/usage, even on operational failure."""
        run = LabourRun(PointResult(company_id, 7, None, 'pending', 'Point 7 pending.'))
        started = monotonic()
        with self._observation('assess-labour', company_id,
                               input={'point': 7, 'prompt_version': PROMPT_VERSION}) as span:
            run.trace_id = span.trace_id
            try:
                timeout = min(COMPANY_DEADLINE_SECONDS, deadline_seconds) \
                    if deadline_seconds is not None else COMPANY_DEADLINE_SECONDS
                await asyncio.wait_for(self._workflow(run, tools), timeout)
            except LabourFailure:
                pass  # Boundary already recorded the operational reason.
            except asyncio.TimeoutError as error:
                code = 'batch_deadline' if deadline_seconds is not None \
                    and deadline_seconds < COMPANY_DEADLINE_SECONDS else 'deadline'
                self._diagnose(run, 'company', code, type(error).__name__)
            except Exception as error:
                # Cancellation inherits BaseException and must propagate.
                self._diagnose(run, 'company', 'internal_error', type(error).__name__)
            run.duration_seconds = round(monotonic() - started, 6)
            span.update(output={**asdict(run.point_result), 'interviews_used': run.interviews_used,
                                'model_calls': run.model_calls, 'usage': run.usage,
                                'duration_seconds': run.duration_seconds},
                        level='DEFAULT' if run.point_result.status == 'complete' else 'WARNING'
                        if run.point_result.status == 'insufficient_evidence' else 'ERROR')
        return run

    async def assess_companies(self, companies: dict[str, list[BaseTool]], *,
                               concurrency: int = COMPANY_CONCURRENCY) -> dict[str, LabourRun]:
        if not 1 <= concurrency <= COMPANY_CONCURRENCY:
            raise ValueError('Company concurrency must be 1 or 2')
        semaphore = asyncio.Semaphore(concurrency)
        batch_end = monotonic() + BATCH_DEADLINE_SECONDS

        async def run(name: str, tools: list[BaseTool]) -> tuple[str, LabourRun]:
            async with semaphore:
                remaining = batch_end - monotonic()
                if remaining <= 0:
                    result = LabourRun(PointResult(name, 7, None, 'error',
                        'Point 7 unresolved (batch_deadline); no supported investment verdict.',
                        diagnostics=(Diagnostic('batch', 'batch_deadline', 'TimeoutError'),)))
                else:
                    result = await self.assess(name, tools, deadline_seconds=remaining)
                return name, result

        return dict(await asyncio.gather(*(run(name, tools) for name, tools in companies.items())))

    async def _retrieve(self, run: LabourRun, interview: BaseTool, role: str) -> None:
        stage = f'retrieve-labour-{role}'
        run.interviews_used += 1  # Attempts are bounded; never retry a budget-consuming call.
        try:
            answer = await asyncio.wait_for(interview.ainvoke(
                dict(role=role, topic='working_conditions'),
                config=self._config(run.point_result.company_id, stage)), TOOL_TIMEOUT_SECONDS)
            if (not isinstance(answer, str) or not answer.strip() or answer.lstrip().startswith(
                    ('Interview limit reached', 'Unknown role ', 'Unknown topic '))):
                raise ValueError('Interview returned no usable evidence')
        except Exception as error:
            self._diagnose(run, stage, 'retrieval_error', type(error).__name__)
            raise LabourFailure() from error
        run.evidence.append(LabourEvidence(run.point_result.company_id,
                                           f'{role}:working_conditions', role, answer))

    async def _classify(self, run: LabourRun, stage: str) -> LabourAssessment:
        with self._observation(stage, run.point_result.company_id,
                               input=[asdict(e) for e in run.evidence]) as span:
            for attempt in range(PARSING_RETRIES + 1):
                try:
                    finding = await asyncio.wait_for(self._interpreter.classify(
                        run, self._config(run.point_result.company_id, stage), retry=attempt > 0),
                        MODEL_TIMEOUT_SECONDS)
                    run.assessments.append(finding)
                    span.update(output=finding.model_dump())
                    return finding
                except InvalidAssessment as error:
                    self._diagnose(run, stage, 'invalid_output', type(error).__name__)
                    if attempt == PARSING_RETRIES:
                        span.update(output={'status': 'invalid_output'}, level='ERROR')
                        raise LabourFailure() from error
                except Exception as error:
                    self._diagnose(run, stage, 'api_error', type(error).__name__)
                    span.update(output={'status': 'api_error'}, level='ERROR')
                    raise LabourFailure() from error
        raise AssertionError('Classification budget exhausted')

    async def _workflow(self, run: LabourRun, tools: list[BaseTool]) -> None:
        interviews = [t for t in tools if t.name == 'interview']
        if len(interviews) != 1:
            self._diagnose(run, 'retrieve-labour-current_employee', 'retrieval_error', 'MissingInterviewTool')
            raise LabourFailure()
        for role, stage in (('current_employee', 'classify-labour-initial'),
                            ('former_employee', 'reassess-labour')):
            await self._retrieve(run, interviews[0], role)
            finding = await self._classify(run, stage)
            if finding.verdict != 'UNCERTAIN':
                self._set_result(run, 'complete',
                    f'Point 7 {finding.verdict}: {finding.evidence_id}: "{finding.evidence}" '
                    f'Interpretation: {finding.reasoning}', finding)
                return
            self._diagnose(run, stage, 'insufficient_evidence', 'UncertainAssessment')
        self._set_result(run, 'insufficient_evidence',
            'Point 7 unresolved after both employee interviews; no supported investment verdict.')
