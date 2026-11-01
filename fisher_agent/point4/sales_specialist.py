"""Fixed Point 4 workflow over already company-scoped lecturer tools."""
import asyncio
import logging
from contextlib import nullcontext
from dataclasses import asdict
from time import monotonic

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from observability.tracing import Observation, Tracing

from .sales_records import InterviewEvidence, ResultStatus, SalesAssessment, SalesResult
from .evidence_interpreter import EvidenceInterpreter, PROMPT_VERSION
from .result_validator import InvalidAssessment

LOGGER = logging.getLogger(__name__)
PARSING_RETRIES = 1
MODEL_TIMEOUT_SECONDS = 20
TOOL_TIMEOUT_SECONDS = 5
COMPANY_DEADLINE_SECONDS = 90
COMPANY_CONCURRENCY = 2


class RetrievalError(ValueError):
    """No usable interview returned; not a semantic judgement of uncertainty."""


class SalesSpecialist:
    def __init__(self, interpreter: EvidenceInterpreter, tracing: Tracing | None = None):
        self._interpreter = interpreter
        self._tracing = tracing

    def _observation(self, name: str, company_id: str, **kwargs):
        if self._tracing is None:
            return nullcontext(Observation())
        return self._tracing.observation(name, company_id=company_id, fisher_point=4, **kwargs)

    def _config(self, company_id: str, stage: str) -> RunnableConfig:
        config = self._tracing.config(company_id=company_id, fisher_point=4, run_name=stage) \
            if self._tracing is not None else {}
        config.setdefault('metadata', {}).update(
            company_id=company_id, fisher_point='4', prompt_version=PROMPT_VERSION, stage=stage)
        return config

    def _diagnostic(self, result: SalesResult, stage: str, category: ResultStatus,
                    error_type: str) -> None:
        # Provider exception text may include request headers or secrets.
        diagnostic = dict(stage=stage, category=category, error_type=error_type)
        result.diagnostics.append(diagnostic)
        LOGGER.warning('Point 4 company=%s stage=%s category=%s error_type=%s',
                       result.company_id, stage, category, error_type)
        with self._observation('record-sales-diagnostic', result.company_id, input=diagnostic) as span:
            span.update(level='ERROR' if category != 'insufficient_evidence' else 'WARNING',
                        output=diagnostic)

    async def assess(self, company_id: str, tools: list[BaseTool]) -> SalesResult:
        """Isolate one company. Failures return FAIL with an explicit failure status."""
        result = SalesResult(company_id)
        start = monotonic()
        with self._observation('assess-sales', company_id,
                               input={'point': 4, 'prompt_version': PROMPT_VERSION}) as span:
            result.trace_id = span.trace_id
            try:
                await asyncio.wait_for(self._workflow(result, tools), COMPANY_DEADLINE_SECONDS)
            except InvalidAssessment:
                result.status = 'invalid_output'
            except RetrievalError:
                result.status = 'retrieval_error'
            except asyncio.TimeoutError as error:
                result.status = 'deadline'
                self._diagnostic(result, 'company', result.status, type(error).__name__)
            except Exception as error:
                # The company boundary preserves the batch, not cancellation.
                result.status = 'internal_error'
                self._diagnostic(result, 'company', result.status, type(error).__name__)
            result.duration_seconds = round(monotonic() - start, 3)
            span.update(output={**result.public_result(), 'status': result.status,
                                'fallback_triggered': result.fallback_triggered,
                                'adjudication_used': result.adjudication_used,
                                'interviews_used': result.interviews_used,
                                'model_calls': result.model_calls, 'usage': result.usage,
                                'diagnostics': result.diagnostics},
                        level='DEFAULT' if result.status in ('assessed', 'adjudicated') else 'ERROR')
        return result

    async def assess_companies(self, companies: dict[str, list[BaseTool]], *,
                               concurrency: int = COMPANY_CONCURRENCY) -> dict[str, SalesResult]:
        """Two workers by default; evidence and budgets stay within each result."""
        if not 1 <= concurrency <= COMPANY_CONCURRENCY:
            raise ValueError('Company concurrency must be 1 or 2')
        semaphore = asyncio.Semaphore(concurrency)

        async def run(name: str, tools: list[BaseTool]) -> tuple[str, SalesResult]:
            async with semaphore:
                return name, await self.assess(name, tools)

        return dict(await asyncio.gather(*(run(name, tools) for name, tools in companies.items())))

    async def _retrieve(self, result: SalesResult, interview: BaseTool, role: str) -> None:
        stage = f'retrieve-sales-{role}'
        result.interviews_used += 1  # Count attempts; never repeat a budget-consuming call.
        try:
            answer = await asyncio.wait_for(interview.ainvoke(
                dict(role=role, topic='sales_team'),
                config=self._config(result.company_id, stage)), TOOL_TIMEOUT_SECONDS)
            if (not isinstance(answer, str) or not answer.strip() or answer.startswith(
                    ('Interview limit reached', 'Unknown role ', 'Unknown topic '))):
                raise RetrievalError('Interview returned no usable evidence')
        except Exception as error:
            self._diagnostic(result, stage, 'retrieval_error', type(error).__name__)
            raise RetrievalError('Interview failed') from error
        result.evidence.append(InterviewEvidence(result.company_id, f'{role}:sales_team', role, answer))

    async def _classify(self, result: SalesResult, stage: str, *,
                        adjudicate: bool = False) -> SalesAssessment | None:
        with self._observation(stage, result.company_id,
                               input=[asdict(item) for item in result.evidence]) as span:
            for attempt in range(PARSING_RETRIES + 1):
                try:
                    assessment = await asyncio.wait_for(self._interpreter.classify(
                        result.evidence, result, self._config(result.company_id, stage),
                        adjudicate=adjudicate, retry=attempt > 0), MODEL_TIMEOUT_SECONDS)
                    result.assessments.append(assessment)
                    span.update(output=assessment.model_dump())
                    return assessment
                except InvalidAssessment as error:
                    self._diagnostic(result, stage, 'invalid_output', type(error).__name__)
                    if attempt == PARSING_RETRIES:
                        raise
                except Exception as error:
                    result.status = 'api_error'
                    self._diagnostic(result, stage, result.status, type(error).__name__)
                    span.update(level='ERROR', status_message='api_error')
                    return None
        return None

    async def _workflow(self, result: SalesResult, tools: list[BaseTool]) -> None:
        interviews = [tool for tool in tools if tool.name == 'interview']
        if len(interviews) != 1:
            self._diagnostic(result, 'retrieve-sales-customer', 'retrieval_error', 'MissingInterviewTool')
            raise RetrievalError('Exactly one company interview tool is required')
        for role, stage in (('customer', 'classify-sales-initial'),
                            ('competitor', 'reassess-sales')):
            await self._retrieve(result, interviews[0], role)
            assessment = await self._classify(result, stage)
            if assessment is None:
                return
            if assessment.verdict != 'UNCERTAIN':
                result.verdict = assessment.verdict
                return
            self._diagnostic(result, stage, 'insufficient_evidence', 'UncertainAssessment')
            result.fallback_triggered = True
        result.adjudication_used = True
        assessment = await self._classify(result, 'adjudicate-sales', adjudicate=True)
        if assessment is None:
            return
        if assessment.verdict != 'UNCERTAIN':
            result.verdict = assessment.verdict
            result.status = 'adjudicated'
        else:
            result.status = 'insufficient_evidence'
            self._diagnostic(result, 'adjudicate-sales', result.status, 'NoSupportedVerdict')
