"""FY2025 margin compared with the company's own industry median."""

from fisher_agent.point5.margin_records import MarginResult, SQLTool, StrategyError
from fisher_agent.point5.evidence_retriever import EvidenceError, EvidenceRetriever
from fisher_agent.point5.point_rules import industry_margin_passes


class IndustryMarginStrategy:
    name = 'industry'

    def evaluate(self, company_id: str, sql_query: SQLTool) -> MarginResult:
        retriever = EvidenceRetriever(company_id, sql_query)
        try:
            margins = retriever.annual_margins((2025,))
            median = retriever.industry_median()
            verdict = 'PASS' if industry_margin_passes(margins[0].margin_pct, median) else 'FAIL'
        except EvidenceError as error:
            return MarginResult(company_id, self.name, 'error', None, str(error),
                                tuple(retriever.evidence),
                                error=StrategyError(error.code, str(error)))
        return MarginResult(
            company_id, self.name, 'complete', verdict,
            f'FY2025 margin {margins[0].margin_pct:.4f}% vs industry median {median}%; '
            f'PASS requires margin >= median. Sources: '
            + ', '.join(item.evidence_id for item in retriever.evidence),
            tuple(retriever.evidence), margins, median,
        )
