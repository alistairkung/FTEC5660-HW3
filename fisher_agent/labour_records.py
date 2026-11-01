"""Point 7's typed interpretations and auditable execution record."""
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import PointResult


class LabourAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    verdict: Literal['PASS', 'FAIL', 'UNCERTAIN']
    evidence: str = Field(min_length=1, max_length=3000)
    evidence_id: str
    reasoning: str = Field(min_length=1, max_length=600)


@dataclass(frozen=True)
class LabourEvidence:
    company_id: str
    evidence_id: str
    role: str
    answer: str
    source_tool: str = 'interview'
    topic: str = 'working_conditions'


@dataclass
class LabourRun:
    point_result: PointResult
    evidence: list[LabourEvidence] = field(default_factory=list)
    assessments: list[LabourAssessment] = field(default_factory=list)
    interviews_used: int = 0
    model_calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    trace_id: str | None = None
    duration_seconds: float = 0
