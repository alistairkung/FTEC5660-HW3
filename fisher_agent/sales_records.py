"""Owned records at the interview, interpretation and specialist boundaries."""
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResultStatus = Literal['assessed', 'adjudicated', 'insufficient_evidence',
                       'invalid_output', 'api_error', 'retrieval_error',
                       'deadline', 'internal_error']


class SalesAssessment(BaseModel):
    """A concise interpretation, supported by an exact quote from one source."""

    model_config = ConfigDict(extra='forbid', strict=True)
    verdict: Literal['PASS', 'FAIL', 'UNCERTAIN']
    evidence: str = Field(min_length=1, max_length=3000)
    evidence_id: str = Field(description='The supplied interview ID supporting the quote')
    reasoning: str = Field(min_length=1, max_length=600)


@dataclass(frozen=True)
class InterviewEvidence:
    company_id: str
    evidence_id: str
    role: str
    answer: str
    source_tool: str = 'interview'
    topic: str = 'sales_team'


@dataclass
class SalesResult:
    company_id: str
    verdict: Literal['PASS', 'FAIL'] = 'FAIL'
    status: ResultStatus = 'assessed'
    evidence: list[InterviewEvidence] = field(default_factory=list)
    assessments: list[SalesAssessment] = field(default_factory=list)
    interviews_used: int = 0
    model_calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    fallback_triggered: bool = False
    adjudication_used: bool = False
    diagnostics: list[dict[str, str]] = field(default_factory=list)
    trace_id: str | None = None
    duration_seconds: float = 0.0

    def public_result(self) -> dict:
        """Point-only development adapter; never claims full homework coverage."""
        if self.status in ('assessed', 'adjudicated'):
            finding = self.assessments[-1]
            summary = (f'Point 4 {self.verdict}: {finding.evidence_id}: '
                       f'"{finding.evidence}" Interpretation: {finding.reasoning}')
        else:
            summary = (f'Point 4 FAIL fallback ({self.status}); no supported final assessment. '
                       'See diagnostics; this is not an evidence-backed investment FAIL.')
        return {'points': {4: self.verdict}, 'summary': summary}
