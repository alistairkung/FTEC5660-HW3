"""Explicit adapters preserve specialist records and reject operational verdicts."""
from .contracts import Diagnostic, PointResult, ProvenanceReference
from .margin_records import MarginResult
from .sales_records import SalesResult


def adapt_sales(result: SalesResult) -> PointResult:
    provenance = tuple(ProvenanceReference(e.evidence_id, e.company_id, e.source_tool)
                       for e in result.evidence)
    diagnostics = tuple(Diagnostic(d['stage'], d['category'], d.get('error_type'))
                        for d in result.diagnostics)
    supported = (result.status in ('assessed', 'adjudicated') and result.assessments
                 and result.assessments[-1].verdict == result.verdict)
    if supported:
        return PointResult(result.company_id, 4, result.verdict, 'complete',
                           result.public_result()['summary'], provenance, diagnostics)
    status = 'insufficient_evidence' if result.status == 'insufficient_evidence' else 'error'
    return PointResult(result.company_id, 4, None, status,
                       f'Point 4 unresolved ({result.status}); no supported investment verdict.',
                       provenance, diagnostics or (Diagnostic('sales', result.status),))


def adapt_margin(result: MarginResult) -> PointResult:
    provenance = tuple(ProvenanceReference(e.evidence_id, e.company_id, e.source_tool)
                       for e in result.evidence)
    diagnostics = ((Diagnostic('margin', result.error.code),) if result.error else ())
    return PointResult(result.company_id, 5, result.verdict, result.status,
                       f'Point 5: {result.summary}', provenance, diagnostics)
