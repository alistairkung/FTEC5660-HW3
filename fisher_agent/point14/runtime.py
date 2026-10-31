"""Construct only the assignment's required model; no network at import."""
from langchain_deepseek import ChatDeepSeek
from hw3 import MODEL_NAME
from observability import Tracing

from .model_gateway import MODEL_TIMEOUT_SECONDS
from .transparency_specialist import TransparencySpecialist


def build_transparency_specialist(tracing: Tracing | None = None) -> TransparencySpecialist:
    model = ChatDeepSeek(model=MODEL_NAME, temperature=0, timeout=MODEL_TIMEOUT_SECONDS,
                         max_retries=0, max_tokens=3500)
    return TransparencySpecialist(model, tracing)
