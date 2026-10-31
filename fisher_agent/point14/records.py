"""Point 14 owned intermediate records; shared PointResult is not yet published."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

PERIODS = ('2025Q3', '2025Q4', '2026Q1', '2026Q2')
Assessment = Literal['TRANSPARENT', 'EVASIVE', 'UNCERTAIN', 'INSUFFICIENT_EVIDENCE']
ResultStatus = Literal['error', 'assessed', 'adjudicated', 'api_error',
                       'retrieval_error', 'invalid_output', 'deadline', 'insufficient_evidence']


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
class QuarterlyReturns:
    period: str
    units_shipped: Decimal
    units_returned: Decimal
    rate_pct: Decimal | None
    source_id: str
    status: Literal['complete', 'zero_denominator'] = 'complete'


@dataclass(frozen=True)
class FinancialSnapshot:
    metrics: tuple[FinancialMetric, ...]
    source: Source
    returns: tuple[QuarterlyReturns, ...] = ()


@dataclass(frozen=True)
class Transcript:
    period: str
    name: str
    source: Source


@dataclass(frozen=True)
class SourcedProposition:
    subject: str = 'unknown'
    metric: str = 'unknown'
    period: str | None = None
    assertion_type: str = 'unknown'
    value: Decimal | None = None
    unit: str | None = None
    basis: str | None = None
    comparator_period: str | None = None
    direction: str | None = None
    qualifiers: tuple[str, ...] = ()
    certainty: Literal['asserted', 'qualified', 'unknown'] = 'unknown'
    measurement_definition: str | None = None
    definition_quotation: str | None = None
    qualitative_text: str | None = None
    assertion_quotation: str | None = None
    measurement_definition_source: Literal['quoted', 'assignment_standard', 'unknown'] = 'unknown'


@dataclass(frozen=True)
class ManagementClaim:
    evidence_id: str
    document: str
    period: str
    topic: str
    quotation: str
    kind: Literal['acknowledges_setback', 'favourable', 'explanation']
    proposition: SourcedProposition | None = None
    company_id: str = ''
    source_id: str = ''
    speaker: str = ''
    communication_date: str | None = None
    span_start: int | None = None
    span_end: int | None = None


@dataclass(frozen=True)
class EvidenceFact:
    evidence_id: str
    company_id: str
    subject: str
    metric: str
    period: str
    basis: str
    value: Decimal | None
    unit: str
    source_id: str
    comparator_period: str | None = None
    comparison_value: Decimal | None = None
    absolute_change: Decimal | None = None
    percentage_change: Decimal | None = None
    denominator: Decimal | None = None
    measurement_definition: str | None = None


@dataclass(frozen=True)
class ClaimEvidenceMatch:
    claim_id: str
    fact_id: str | None
    compatibility: Literal['COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN']
    relation: Literal['SUPPORTED', 'CONTRADICTED', 'INCONCLUSIVE', 'UNMATCHED']
    reason: str


@dataclass(frozen=True)
class AdverseEvent:
    evidence_id: str
    metric: str
    period: str
    fact_ids: tuple[str, ...]
    status: Literal['candidate'] = 'candidate'


@dataclass(frozen=True)
class CommunicationCoverage:
    scope: Literal['four_supplied_earnings_calls']
    expected_periods: tuple[str, ...]
    retrieved_periods: tuple[str, ...]
    complete: bool
    gaps: tuple[str, ...]
    claim_extraction_scope: str = 'bounded_candidates_not_exhaustive'
    knowledge_policy: str = 'same_event_acknowledgement_in_supplied_calls_only'


@dataclass(frozen=True)
class DisclosureFinding:
    event_id: str
    relation: Literal['ACKNOWLEDGED', 'NOT_FOUND', 'INCONCLUSIVE']
    claim_ids: tuple[str, ...]
    materiality: Literal['MATERIAL', 'IMMATERIAL', 'UNKNOWN']
    knowledge: Literal['ESTABLISHED', 'UNKNOWN']
    materiality_claim_ids: tuple[str, ...] = ()
    knowledge_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransparencyDecision:
    assessment: Literal['TRANSPARENT', 'EVASIVE', 'INSUFFICIENT_EVIDENCE']
    reasons: tuple[str, ...]
    matches: tuple[ClaimEvidenceMatch, ...]
    disclosures: tuple[DisclosureFinding, ...]
    policy_version: str = 'scoped-disclosure-prerequisites-v1'


@dataclass
class Diagnostics:
    model_calls: int = 0
    parsing_retries: int = 0
    quotation_rejections: int = 0
    adjudications: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    model_latency_seconds: float = 0.0
    claim_extraction_scope: str = 'bounded_candidates_not_exhaustive'
    claim_counts: dict[str, int] = field(default_factory=dict)
    claim_cap_periods: list[str] = field(default_factory=list)
    validation_rejections: list[str] = field(default_factory=list)
    normalization_notes: list[str] = field(default_factory=list)


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
    facts: tuple[EvidenceFact, ...] = ()
    events: tuple[AdverseEvent, ...] = ()
    coverage: CommunicationCoverage | None = None
    decision: TransparencyDecision | None = None
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    error_stage: str | None = None
    error_type: str | None = None
    trace_id: str | None = None
    duration_seconds: float = 0.0

    def public_result(self) -> dict:
        if self.verdict is None:
            return {'points': {14: 'FAIL'}, 'summary':
                    f'Point 14 FAIL fallback ({self.status}, {self.error_stage}); '
                    'no supported transparency verdict. ' + self.reason[:600]}
        return {'points': {14: self.verdict}, 'summary': self.reason}
