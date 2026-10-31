"""Independent, bounded Point 14 pipeline. No multi-point orchestration."""
import asyncio
from time import monotonic
from typing import Any

from observability import Tracing
from observability.tracing import current_tracing

from .financial_evidence_extractor import FinancialEvidenceExtractor
from .management_claim_extractor import ManagementClaimExtractor
from .model_gateway import ModelGateway
from .records import EvidenceError, ModelOutputError, PERIODS, Source, Transcript, TransparencyResult
from .transparency_verifier import TransparencyVerifier, render_reason

COMPANY_DEADLINE_SECONDS = 180


class TransparencySpecialist:
    def __init__(self, model: Any, tracing: Tracing | None = None):
        self.model = model
        active = tracing or current_tracing()
        self._owns_tracing = active is None
        self.tracing = active if active is not None else Tracing()

    def close(self) -> None:
        """Close an internally created lifecycle after ALL company tasks finish."""
        if self._owns_tracing:
            self.tracing.close()

    async def evaluate(self, company_id: str, tools: list[Any]) -> TransparencyResult:
        result = TransparencyResult(company_id)
        start = monotonic()
        with self.tracing.observation('point14', company_id=company_id, fisher_point=14,
                                      input={'periods': PERIODS}) as root:
            result.trace_id = root.trace_id
            try:
                await asyncio.wait_for(self._run(result, tools), COMPANY_DEADLINE_SECONDS)
            except TimeoutError:
                result.status, result.error_type = 'deadline', 'TimeoutError'
            except ModelOutputError:
                result.status, result.error_type = 'invalid_output', 'ModelOutputError'
            except EvidenceError:
                result.status, result.error_type = 'retrieval_error', 'EvidenceError'
            except Exception as exc:
                # This company boundary must preserve the batch and never retain secrets.
                result.status = ('api_error' if result.error_stage in (
                    'claim-extraction', 'transparency-verification', 'final-adjudication')
                    else 'retrieval_error')
                result.error_type = type(exc).__name__
            result.duration_seconds = monotonic() - start
            with self.tracing.observation('point14.final-verdict', company_id=company_id,
                                          fisher_point=14) as final:
                final.update(output={'verdict': result.verdict, 'status': result.status,
                                     'assessment': result.assessment, 'diagnostics': vars(result.diagnostics)})
            root.update(output={'verdict': result.verdict, 'status': result.status,
                                'error_stage': result.error_stage, 'error_type': result.error_type,
                                'duration_seconds': result.duration_seconds})
        return result

    async def _run(self, result: TransparencyResult, tools: list[Any]) -> None:
        by_name = {tool.name: tool for tool in tools}
        if len(by_name) != len(tools) or not {'sql_query', 'list_documents', 'read_document'} <= set(by_name):
            raise EvidenceError('Missing or duplicate supplied tools')
        company = result.company_id
        config = self.tracing.config(company_id=company, fisher_point=14, run_name='point14')
        config.setdefault('metadata', {})['reporting_periods'] = ','.join(PERIODS)
        gateway = ModelGateway(self.model, result.diagnostics, config=config)
        result.error_stage = 'financial-extraction'
        with self.tracing.observation('point14.financial-extraction', company_id=company,
                                      fisher_point=14) as stage:
            result.financial = await FinancialEvidenceExtractor().extract(company, by_name['sql_query'], config=config)
            stage.update(output={'metrics': len(result.financial.metrics), 'periods': PERIODS})
        result.error_stage = 'document-retrieval'
        with self.tracing.observation('point14.document-retrieval', company_id=company,
                                      fisher_point=14) as stage:
            listing = await by_name['list_documents'].ainvoke({}, config=config)
            if not isinstance(listing, str):
                raise EvidenceError('Malformed document listing')
            names = {line.split(':', 1)[0].strip() for line in listing.splitlines()}
            transcripts = []
            for period in PERIODS:
                name = f'earnings_call_{period.lower()}.md'
                if name not in names:
                    raise EvidenceError('Missing required earnings call')
                text = await by_name['read_document'].ainvoke({'name': name}, config=config)
                if not isinstance(text, str) or not text.strip() or text.startswith('No document named'):
                    raise EvidenceError('Failed or empty earnings call')
                transcripts.append(Transcript(period, name, Source(
                    f'doc:{period}', company, 'read_document', {'name': name}, text)))
                result.transcripts = tuple(transcripts)
            stage.update(output={'documents': [doc.name for doc in transcripts]})
        result.error_stage = 'claim-extraction'
        with self.tracing.observation('point14.claim-extraction', company_id=company,
                                      fisher_point=14) as stage:
            result.claims = await ManagementClaimExtractor(gateway, self.tracing).extract(result.transcripts)
            stage.update(output={'claims': [vars(claim) for claim in result.claims],
                                 'retries': result.diagnostics.parsing_retries,
                                 'quotation_rejections': result.diagnostics.quotation_rejections})
        verifier = TransparencyVerifier(gateway)
        result.error_stage = 'transparency-verification'
        with self.tracing.observation('point14.transparency-verification', company_id=company,
                                      fisher_point=14) as stage:
            assessment = await verifier.verify(result.financial, result.claims, result.transcripts)
            result.assessment = assessment.assessment
            result.comparisons = tuple(item.model_dump() for item in assessment.comparisons)
            stage.update(output=assessment.model_dump())
        if assessment.assessment == 'UNCERTAIN':
            result.error_stage = 'final-adjudication'
            with self.tracing.observation('point14.final-adjudication', company_id=company,
                                          fisher_point=14) as stage:
                assessment = await verifier.adjudicate(result.financial, result.claims,
                                                       assessment, result.transcripts)
                stage.update(output=assessment.model_dump())
        result.assessment = assessment.assessment
        result.comparisons = tuple(item.model_dump() for item in assessment.comparisons)
        reason = render_reason(assessment, result.financial, result.claims)
        result.verdict = 'PASS' if assessment.assessment == 'TRANSPARENT' else 'FAIL'
        result.status = 'adjudicated' if result.diagnostics.adjudications else 'assessed'
        result.reason = reason
        result.error_stage = None
