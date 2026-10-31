"""Three positive annual margins and an FY2025 margin at least FY2023's."""

from fisher_agent.margin_records import MarginResult, SQLTool, StrategyError
from fisher_agent.evidence_retriever import EvidenceError, EvidenceRetriever
from fisher_agent.point_rules import historical_margin_passes


class HistoricalMarginStrategy:
    name = 'historical'

    def evaluate(self, company_id: str, sql_query: SQLTool) -> MarginResult:
        retriever = EvidenceRetriever(company_id, sql_query)
        try:
            margins = retriever.annual_margins((2023, 2024, 2025))
            passes = historical_margin_passes({item.year: item.margin_pct for item in margins})
        except EvidenceError as error:
            return MarginResult(company_id, self.name, 'error', None, str(error),
                                tuple(retriever.evidence),
                                error=StrategyError(error.code, str(error)))
        return MarginResult(
            company_id, self.name, 'complete', 'PASS' if passes else 'FAIL',
            '; '.join(f'FY{item.year} margin {item.margin_pct:.4f}%' for item in margins)
            + '. PASS requires all margins > 0 and FY2025 >= FY2023. Source: '
            + margins[0].evidence_id,
            tuple(retriever.evidence), margins,
        )
