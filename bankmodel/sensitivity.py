"""One-at-a-time sensitivity: move each driver up and down and measure the change in an output."""
from __future__ import annotations

from dataclasses import replace

from .model import Assumptions, project

# Drivers to test and how far to move them (absolute change for rates, relative for volumes/costs).
DRIVERS: dict[str, tuple[str, float, str]] = {
    # key: (label, shock, mode)  mode "abs" = +/- shock in rate points, "rel" = +/- shock as % of value
    "loan_yield": ("Loan yield +/-1pp", 0.01, "abs"),
    "cost_of_risk": ("Write-off rate +/-1pp", 0.01, "abs"),
    "deposit_rate": ("Deposit rate +/-0.5pp", 0.005, "abs"),
    "liquidity_ratio": ("Liquidity buffer +/-5pp", 0.05, "abs"),
    "cac_rate": ("Acquisition cost +/-1pp", 0.01, "abs"),
    "fixed_opex": ("Fixed opex +/-10%", 0.10, "rel"),
    "originations": ("Originations +/-20%", 0.20, "rel"),
}


def _shock(a: Assumptions, key: str, shock: float, mode: str, sign: int) -> Assumptions:
    value = getattr(a, key)
    if isinstance(value, list):
        new = [v * (1 + sign * shock) for v in value] if mode == "rel" else [v + sign * shock for v in value]
    else:
        new = value * (1 + sign * shock) if mode == "rel" else value + sign * shock
    return replace(a, **{key: new})


def _cum_profit(a: Assumptions, years: int) -> float:
    return sum(y.net_profit for y in project(a, years))


def sensitivity(a: Assumptions, years: int = 5) -> list[dict[str, float | str]]:
    """Return rows sorted by impact on cumulative 5-year net profit (largest swing first)."""
    base = _cum_profit(a, years)
    rows = []
    for key, (label, shock, mode) in DRIVERS.items():
        up = _cum_profit(_shock(a, key, shock, mode, +1), years) - base
        down = _cum_profit(_shock(a, key, shock, mode, -1), years) - base
        rows.append({"driver": label, "up": up, "down": down, "swing": abs(up - down)})
    return sorted(rows, key=lambda r: r["swing"], reverse=True)
