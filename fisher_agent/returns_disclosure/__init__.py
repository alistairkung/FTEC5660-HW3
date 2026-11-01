"""Independent Point 14 returns experiment; no client construction on import."""
from observability import Tracing

from .point14_returns_strategy import Point14ReturnsStrategy, MODEL_TIMEOUT_SECONDS


def build_returns_strategy(tracing: Tracing | None = None) -> Point14ReturnsStrategy:
    from langchain_deepseek import ChatDeepSeek
    from hw3 import MODEL_NAME

    model = ChatDeepSeek(model=MODEL_NAME,temperature=0,max_tokens=600,
        timeout=MODEL_TIMEOUT_SECONDS,max_retries=0,
        extra_body={'thinking':{'type':'disabled'}})
    return Point14ReturnsStrategy(model,tracing)


__all__ = ['Point14ReturnsStrategy','build_returns_strategy']
