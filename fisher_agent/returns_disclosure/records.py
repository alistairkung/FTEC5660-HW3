"""Owned records for the narrow returns-disclosure experiment."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fisher_agent.contracts import Diagnostic, PointResult


class EvidenceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SourceEvidence:
    evidence_id: str
    company_id: str
    source_tool: str
    arguments: dict[str, str]
    raw: str


@dataclass(frozen=True)
class CallDocument:
    period: str
    name: str
    date: str
    source: SourceEvidence


@dataclass(frozen=True)
class QuarterReturns:
    period: str
    shipped: int
    returned: int
    source_id: str
    company_id: str


@dataclass(frozen=True)
class RateComparison:
    """Rates are percentages (100 * returned / shipped); ratio is a multiplier.

    These Decimal displays are informational; anomaly decisions use integer products.
    """
    period: str
    shipped: int
    returned: int
    baseline_shipped: int
    baseline_returned: int
    anomalous: bool
    ratio: Decimal | None
    zero_baseline: bool
    company_id: str
    source_id: str
    current_rate: Decimal
    baseline_rate: Decimal


class DisclosureAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    document: str
    quarter: str
    classification: Literal['ACKNOWLEDGED', 'NOT_ACKNOWLEDGED', 'UNCERTAIN']
    quotation: str | None
    speaker: str | None
    full_call_inspected: bool
    reason: str = Field(min_length=1, max_length=400)


@dataclass(frozen=True)
class EventFinding:
    period: str
    document: str
    source_id: str
    classification: Literal['ACKNOWLEDGED', 'NOT_ACKNOWLEDGED', 'UNCERTAIN']
    quotation: str | None
    speaker: str | None
    reason: str


@dataclass
class ReturnsRun:
    point_result: PointResult
    quarters: tuple[QuarterReturns, ...] = ()
    comparisons: tuple[RateComparison, ...] = ()
    evidence: list[SourceEvidence] = field(default_factory=list)
    findings: list[EventFinding] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    model_calls: int = 0
    format_repairs: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: dict[str, int] = field(default_factory=dict)
    trace_id: str | None = None
    duration_seconds: float = 0
    failure_status: Literal['error', 'insufficient_evidence'] | None = None
