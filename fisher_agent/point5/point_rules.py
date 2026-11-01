"""Deterministic Point 5 calculations. Margins are percentage points."""

from decimal import Decimal


def operating_margin_pct(revenue: Decimal, operating_costs: Decimal) -> Decimal:
    if not revenue.is_finite() or not operating_costs.is_finite():
        raise ValueError("Revenue and operating costs must be finite")
    if revenue <= 0:
        raise ValueError("Revenue must be positive to define an operating margin")
    return (revenue - operating_costs) / revenue * Decimal(100)


def industry_margin_passes(margin_pct: Decimal, median_pct: Decimal) -> bool:
    if not margin_pct.is_finite() or not median_pct.is_finite():
        raise ValueError('Margin and median must be finite')
    return margin_pct >= median_pct


def historical_margin_passes(margins: dict[int, Decimal]) -> bool:
    if set(margins) != {2023, 2024, 2025}:
        raise ValueError('Historical rule needs exactly FY2023, FY2024 and FY2025')
    if not all(margin.is_finite() for margin in margins.values()):
        raise ValueError('Historical margins must be finite')
    return all(margin > 0 for margin in margins.values()) and margins[2025] >= margins[2023]
