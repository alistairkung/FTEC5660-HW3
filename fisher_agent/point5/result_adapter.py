"""Adapt specialist records without treating operational errors as verdicts."""
from ..contracts import Diagnostic, PointResult, ProvenanceReference
from .margin_records import MarginResult


def adapt_margin(result: MarginResult) -> PointResult:
    provenance = tuple(ProvenanceReference(e.evidence_id, e.company_id, e.source_tool)
                       for e in result.evidence)
    diagnostics = ((Diagnostic('margin', result.error.code),) if result.error else ())
    return PointResult(result.company_id, 5, result.verdict, result.status,
                       f'Point 5: {result.summary}', provenance, diagnostics)
