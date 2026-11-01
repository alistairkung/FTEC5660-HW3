"""Deterministic schema and quote checks; source membership is not entailment."""
from .sales_records import InterviewEvidence, SalesAssessment


class InvalidAssessment(ValueError):
    """Malformed structure or unsupported source/quote, rather than uncertainty."""


def validate_assessment(proposal: object, evidence: list[InterviewEvidence]) -> SalesAssessment:
    try:
        assessment = SalesAssessment.model_validate(proposal)
    except ValueError as error:
        raise InvalidAssessment('Malformed assessment') from error
    sources = {item.evidence_id: item for item in evidence}
    if len(sources) != len(evidence) or len({item.company_id for item in evidence}) != 1:
        raise InvalidAssessment('Evidence must have unique IDs within one company')
    source = sources.get(assessment.evidence_id)
    if (source is None or not assessment.evidence.strip() or not assessment.reasoning.strip()
            or assessment.evidence not in source.answer):
        raise InvalidAssessment('Assessment must quote its supplied interview verbatim')
    return assessment
