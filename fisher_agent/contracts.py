"""Minimal shared specialist boundary; evidence records remain specialist-owned."""
from dataclasses import dataclass
from typing import Literal

Verdict = Literal['PASS', 'FAIL']


@dataclass(frozen=True)
class ProvenanceReference:
    evidence_id: str
    company_id: str
    source_tool: str


@dataclass(frozen=True)
class Diagnostic:
    stage: str
    code: str
    error_type: str | None = None


@dataclass(frozen=True)
class PointResult:
    company_id: str
    point: int
    verdict: Verdict | None
    status: Literal['complete', 'error', 'insufficient_evidence', 'pending']
    summary: str
    provenance: tuple[ProvenanceReference, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not self.company_id or not 1 <= self.point <= 15 or not self.summary.strip():
            raise ValueError('Company, Fisher point and summary are required')
        if self.status == 'complete':
            if self.verdict not in ('PASS', 'FAIL') or not self.provenance:
                raise ValueError('A completed result needs a verdict and provenance')
        elif self.status not in ('error', 'insufficient_evidence', 'pending') or self.verdict is not None:
            raise ValueError('An unresolved result must have no investment verdict')
        ids = [item.evidence_id for item in self.provenance]
        if len(ids) != len(set(ids)) or any(
            item.company_id != self.company_id for item in self.provenance
        ):
            raise ValueError('Provenance must be unique and company-scoped')
