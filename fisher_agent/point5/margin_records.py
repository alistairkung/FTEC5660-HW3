"""Typed Point 5 strategy boundary; operational errors have no verdict."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol


class SQLTool(Protocol):
    def invoke(self, input: dict[str, str]) -> str: ...


@dataclass(frozen=True)
class SQLEvidence:
    evidence_id: str
    company_id: str
    query: str
    raw_result: str | None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    source_tool: Literal['sql_query'] = 'sql_query'


@dataclass(frozen=True)
class AnnualMargin:
    year: int
    revenue: Decimal
    operating_costs: Decimal
    margin_pct: Decimal
    evidence_id: str


@dataclass(frozen=True)
class StrategyError:
    code: str
    message: str


@dataclass(frozen=True)
class MarginResult:
    company_id: str
    strategy: str
    status: Literal['complete', 'error']
    verdict: Literal['PASS', 'FAIL'] | None
    summary: str
    evidence: tuple[SQLEvidence, ...] = ()
    margins: tuple[AnnualMargin, ...] = ()
    industry_median_pct: Decimal | None = None
    error: StrategyError | None = None

    def __post_init__(self) -> None:
        if self.status == 'complete':
            if self.verdict not in ('PASS', 'FAIL') or self.error is not None:
                raise ValueError('A completed result needs a verdict and no error')
            if not self.evidence or not self.margins:
                raise ValueError('A completed result needs evidence and derived margins')
            references = {item.evidence_id for item in self.evidence}
            if len(references) != len(self.evidence) or any(
                item.company_id != self.company_id for item in self.evidence
            ):
                raise ValueError('Evidence IDs must be unique and belong to this company')
            if any(margin.evidence_id not in references for margin in self.margins):
                raise ValueError('Derived margins must reference supplied SQL evidence')
        elif self.status != 'error' or self.verdict is not None or self.error is None:
            raise ValueError('An error result needs an error and no verdict')


class MarginStrategy(Protocol):
    name: str

    def evaluate(self, company_id: str, sql_query: SQLTool) -> MarginResult: ...
