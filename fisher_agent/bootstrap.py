"""Application composition; importing this module creates no clients or tools."""
from observability import Tracing, current_tracing

from .company_analyzer import CompanyAnalyzer
from .point4.evidence_interpreter import EvidenceInterpreter
from .point4.sales_specialist import MODEL_TIMEOUT_SECONDS as SALES_MODEL_TIMEOUT_SECONDS
from .point4.sales_specialist import SalesSpecialist
from .point5.industry_margin_strategy import IndustryMarginStrategy
from .point5.margin_runner import MarginRunner
from .point14 import Point14ReturnsStrategy
from .point14.point14_returns_strategy import MODEL_TIMEOUT_SECONDS as RETURNS_MODEL_TIMEOUT_SECONDS


def build_sales_specialist(model_name: str, tracing: Tracing | None = None) -> SalesSpecialist:
    from langchain_deepseek import ChatDeepSeek

    model = ChatDeepSeek(model=model_name, temperature=0, max_tokens=600,
                         timeout=SALES_MODEL_TIMEOUT_SECONDS, max_retries=0,
                         extra_body={'thinking': {'type': 'disabled'}})
    return SalesSpecialist(EvidenceInterpreter(model), tracing)


def build_returns_strategy(model_name: str, tracing: Tracing | None = None) -> Point14ReturnsStrategy:
    from langchain_deepseek import ChatDeepSeek

    model = ChatDeepSeek(model=model_name, temperature=0, max_tokens=600,
                         timeout=RETURNS_MODEL_TIMEOUT_SECONDS, max_retries=0,
                         extra_body={'thinking': {'type': 'disabled'}})
    return Point14ReturnsStrategy(model, tracing)


def build_agent(model_name: str) -> CompanyAnalyzer:
    """Construct the selected specialists once, sharing the optional trace lifecycle."""
    tracing = current_tracing()
    return CompanyAnalyzer(
        build_sales_specialist(model_name, tracing),
        MarginRunner(IndustryMarginStrategy(), tracing=tracing),
        returns_strategy=build_returns_strategy(model_name, tracing), tracing=tracing,
    )
