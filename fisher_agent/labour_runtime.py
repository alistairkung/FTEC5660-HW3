"""Point 7 construction boundary; credentials/clients are never loaded on import."""
from langchain_deepseek import ChatDeepSeek

from hw3 import MODEL_NAME
from observability import Tracing

from .labour_specialist import LabourSpecialist, MODEL_TIMEOUT_SECONDS


def build_labour_specialist(tracing: Tracing | None = None) -> LabourSpecialist:
    model = ChatDeepSeek(model=MODEL_NAME, temperature=0, max_tokens=600,
                         timeout=MODEL_TIMEOUT_SECONDS, max_retries=0,
                         extra_body={'thinking': {'type': 'disabled'}})
    return LabourSpecialist(model, tracing)
