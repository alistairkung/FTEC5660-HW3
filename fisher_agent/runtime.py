"""Construct the permitted model once; no clients or credentials at import."""
from langchain_deepseek import ChatDeepSeek

from hw3 import MODEL_NAME
from observability import Tracing

from .evidence_interpreter import EvidenceInterpreter
from .sales_specialist import MODEL_TIMEOUT_SECONDS, SalesSpecialist


def build_sales_specialist(tracing: Tracing | None = None) -> SalesSpecialist:
    model = ChatDeepSeek(model=MODEL_NAME, temperature=0, max_tokens=600,
                         timeout=MODEL_TIMEOUT_SECONDS, max_retries=0,
                         extra_body={'thinking': {'type': 'disabled'}})
    return SalesSpecialist(EvidenceInterpreter(model), tracing)
