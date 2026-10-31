"""Point 14 owned intermediate records; shared PointResult is not yet published."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

PERIODS = ('2025Q3', '2025Q4', '2026Q1', '2026Q2')
Assessment = Literal['TRANSPARENT', 'EVASIVE', 'UNCERTAIN']
ResultStatus = Literal['error', 'assessed', 'adjudicated', 'api_error',
                       'retrieval_error', 'invalid_output', 'deadline']


class EvidenceError(ValueError):
    """Retrieved or proposed evidence failed deterministic validation."""


class ModelOutputError(ValueError):
    """Structured model output remained invalid after bounded recovery."""


@dataclass(frozen=True)
class Source:
    evidence_id: str
    company_id: str
    tool: str
    arguments: dict[str, str]
    raw: str


@dataclass(frozen=True)
class FinancialMetric:
    evidence_id: str
    period: str
    metric: str
    value: Decimal
    unit: Literal['USD_thousands', 'percent']
    source_id: str
    comparison_period: str | None = None
    comparison_value: Decimal | None = None
    absolute_change: Decimal | None = None
    percentage_change: Decimal | None = None
    comparison_status: Literal['available', 'zero_denominator', 'level'] = 'level'


@dataclass(frozen=True)
class FinancialSnapshot:
    metrics: tuple[FinancialMetric, ...]
    source: Source


@dataclass(frozen=True)
class Transcript:
    period: str
    name: str
    source: Source


@dataclass(frozen=True)
class ManagementClaim:
    evidence_id: str
    document: str
    period: str
    topic: str
    quotation: str
    kind: Literal['acknowledges_setback', 'favourable', 'explanation']


@dataclass
class Diagnostics:
    model_calls: int = 0
    parsing_retries: int = 0
    quotation_rejections: int = 0
    adjudications: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    model_latency_seconds: float = 0.0


@dataclass
class TransparencyResult:
    """Pipeline result pending the separately owned shared PointResult adapter.

    Errors carry no verdict. public_result explicitly labels its FAIL fallback.
    """
    company_id: str
    point_id: int = field(default=14, init=False)
    verdict: Literal['PASS', 'FAIL'] | None = None
    status: ResultStatus = 'error'
    reason: str = ''
    assessment: Assessment | None = None
    financial: FinancialSnapshot | None = None
    transcripts: tuple[Transcript, ...] = ()
    claims: tuple[ManagementClaim, ...] = ()
    comparisons: tuple[dict, ...] = ()
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    error_stage: str | None = None
    error_type: str | None = None
    trace_id: str | None = None
    duration_seconds: float = 0.0

    def public_result(self) -> dict:
        if self.verdict is None:
            return {'points': {14: 'FAIL'}, 'summary':
                    f'Point 14 FAIL fallback ({self.status}, {self.error_stage}); '
                    'no supported transparency assessment.'}
        return {'points': {14: self.verdict}, 'summary': self.reason}
