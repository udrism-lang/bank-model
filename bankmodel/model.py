"""Five-year annual projection for a deposit-funded digital consumer lender.

The logic mirrors the companion Excel workbook (Banka_X_finansu_modelis.xlsx) line by line,
so both give identical numbers. All amounts are in EUR millions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Assumptions:
    """Inputs for one scenario. Per-year inputs are lists with one value per year."""

    initial_capital: float
    capital_injection_year3: float
    originations: list[float]
    loan_yield: float
    repayment_rate_opening: float
    repayment_rate_new: float
    cost_of_risk: float
    day1_provision: float
    deposit_rate: float
    liquidity_ratio: float
    liquidity_yield: float
    fee_rate: float
    fixed_opex: list[float]
    cac_rate: float
    servicing_rate: float
    other_assets: float
    tax_rate: float
    risk_weight_loans: float
    op_risk_multiplier: float
    capital_requirement: float
    management_buffer: float


@dataclass
class YearResult:
    year: int
    # Loan book
    opening_loans: float = 0.0
    originations: float = 0.0
    repayments: float = 0.0
    avg_loans: float = 0.0
    credit_losses: float = 0.0
    closing_loans: float = 0.0
    # Balance sheet
    other_assets: float = 0.0
    equity_open: float = 0.0
    deposits: float = 0.0
    liquidity_pre_profit: float = 0.0
    liquidity: float = 0.0
    total_assets: float = 0.0
    total_liabilities_equity: float = 0.0
    # P&L
    interest_loans: float = 0.0
    interest_liquidity: float = 0.0
    interest_deposits: float = 0.0
    nii: float = 0.0
    fees: float = 0.0
    total_income: float = 0.0
    fixed_opex: float = 0.0
    acquisition_cost: float = 0.0
    servicing_cost: float = 0.0
    opex: float = 0.0
    pbt: float = 0.0
    cumulative_pbt: float = 0.0
    tax: float = 0.0
    net_profit: float = 0.0
    # Capital
    capital_injection: float = 0.0
    equity_close: float = 0.0
    rwa_credit: float = 0.0
    rwa_other: float = 0.0
    rwa_operational: float = 0.0
    rwa: float = 0.0
    capital_ratio: float = 0.0
    capital_target: float = 0.0
    capital_surplus: float = 0.0
    leverage_ratio: float = 0.0
    # KPIs
    nim: float = 0.0
    cost_income: float = 0.0
    cost_of_risk_actual: float = 0.0
    roe: float = 0.0
    loan_to_deposit: float = 0.0

    @property
    def balance_check(self) -> float:
        return round(self.total_assets - self.total_liabilities_equity, 9)


@dataclass
class ScenarioResult:
    name: str
    label: str
    assumptions: Assumptions
    years: list[YearResult] = field(default_factory=list)

    def first_profitable_year(self) -> int | None:
        for y in self.years:
            if y.net_profit > 0:
                return y.year
        return None

    def summary(self) -> dict[str, float | int | None]:
        last = self.years[-1]
        return {
            "loans_end": last.closing_loans,
            "deposits_end": last.deposits,
            "total_assets_end": last.total_assets,
            "net_profit_last_year": last.net_profit,
            "cumulative_net_profit": sum(y.net_profit for y in self.years),
            "first_profitable_year": self.first_profitable_year(),
            "roe_last_year": last.roe,
            "cost_income_last_year": last.cost_income,
            "nim_last_year": last.nim,
            "min_capital_ratio": min(y.capital_ratio for y in self.years),
            "max_capital_shortfall": min(y.capital_surplus for y in self.years),
        }


def _safe_div(a: float, b: float) -> float:
    return a / b if b > 0 else 0.0


def project(a: Assumptions, years: int = 5) -> list[YearResult]:
    """Run the projection. Each year uses only the previous year's results, so there is no circularity."""
    out: list[YearResult] = []
    prev: YearResult | None = None

    for i in range(years):
        y = YearResult(year=i + 1)

        # --- Loan book -------------------------------------------------------
        y.opening_loans = prev.closing_loans if prev else 0.0
        y.originations = a.originations[i]
        y.repayments = -(y.opening_loans * a.repayment_rate_opening + y.originations * a.repayment_rate_new)
        gross_close = y.opening_loans + y.originations + y.repayments
        y.avg_loans = (y.opening_loans + gross_close) / 2
        y.credit_losses = -(y.avg_loans * a.cost_of_risk + y.originations * a.day1_provision)
        y.closing_loans = gross_close + y.credit_losses

        # --- Funding ---------------------------------------------------------
        # Deposits are the balancing funding item: enough to fund loans and other assets plus
        # the liquidity buffer, net of equity at the start of the year. From year 2 we also
        # pre-fund last year's loss, as a proxy for this year's (keeps liquidity positive).
        y.other_assets = a.other_assets
        y.equity_open = a.initial_capital if prev is None else prev.equity_close
        y.capital_injection = a.capital_injection_year3 if y.year == 3 else 0.0
        loss_adj = min(0.0, prev.net_profit) if prev else 0.0
        y.deposits = max((y.closing_loans + y.other_assets - y.equity_open - loss_adj) / (1 - a.liquidity_ratio), 0.0)
        y.liquidity_pre_profit = y.deposits + y.equity_open + y.capital_injection - y.closing_loans - y.other_assets

        # --- P&L -------------------------------------------------------------
        y.interest_loans = y.avg_loans * a.loan_yield
        prev_liq = prev.liquidity if prev else 0.0
        y.interest_liquidity = (prev_liq + y.liquidity_pre_profit) / 2 * a.liquidity_yield
        prev_dep = prev.deposits if prev else 0.0
        y.interest_deposits = -(prev_dep + y.deposits) / 2 * a.deposit_rate
        y.nii = y.interest_loans + y.interest_liquidity + y.interest_deposits
        y.fees = y.avg_loans * a.fee_rate
        y.total_income = y.nii + y.fees
        y.fixed_opex = -a.fixed_opex[i]
        y.acquisition_cost = -y.originations * a.cac_rate
        y.servicing_cost = -y.avg_loans * a.servicing_rate
        y.opex = y.fixed_opex + y.acquisition_cost + y.servicing_cost
        y.pbt = y.total_income + y.opex + y.credit_losses
        y.cumulative_pbt = (prev.cumulative_pbt if prev else 0.0) + y.pbt
        y.tax = -max(0.0, min(y.pbt, y.cumulative_pbt)) * a.tax_rate  # simple loss carry-forward
        y.net_profit = y.pbt + y.tax

        # --- Capital and balance sheet close ---------------------------------
        y.equity_close = y.equity_open + y.capital_injection + y.net_profit
        y.liquidity = y.deposits + y.equity_close - y.closing_loans - y.other_assets
        y.total_assets = y.closing_loans + y.liquidity + y.other_assets
        y.total_liabilities_equity = y.deposits + y.equity_close

        y.rwa_credit = y.closing_loans * a.risk_weight_loans
        y.rwa_other = y.other_assets
        y.rwa_operational = max(0.0, y.total_income) * a.op_risk_multiplier
        y.rwa = y.rwa_credit + y.rwa_other + y.rwa_operational
        y.capital_ratio = _safe_div(y.equity_close, y.rwa)
        y.capital_target = a.capital_requirement + a.management_buffer
        y.capital_surplus = y.equity_close - y.capital_target * y.rwa
        y.leverage_ratio = _safe_div(y.equity_close, y.total_assets)

        # --- KPIs ------------------------------------------------------------
        avg_assets = (prev.total_assets + y.total_assets) / 2 if prev else y.total_assets / 2
        y.nim = _safe_div(y.nii, avg_assets)
        y.cost_income = _safe_div(-y.opex, y.total_income)
        y.cost_of_risk_actual = _safe_div(-y.credit_losses, y.avg_loans)
        y.roe = _safe_div(y.net_profit, (y.equity_open + y.equity_close) / 2)
        y.loan_to_deposit = _safe_div(y.closing_loans, y.deposits)

        out.append(y)
        prev = y
    return out


def load_scenarios(path: str | Path) -> tuple[int, dict[str, tuple[str, Assumptions]]]:
    """Read assumptions.yaml and return {scenario_key: (label, Assumptions)}."""
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    years = int(cfg.get("years", 5))
    scenarios: dict[str, tuple[str, Assumptions]] = {}
    for key, meta in cfg["scenarios"].items():
        values = {name: spec[key] for name, spec in cfg["assumptions"].items()}
        scenarios[key] = (meta.get("label", key), Assumptions(**values))
    return years, scenarios


def run_all(path: str | Path) -> list[ScenarioResult]:
    years, scenarios = load_scenarios(path)
    return [
        ScenarioResult(name=key, label=label, assumptions=a, years=project(a, years))
        for key, (label, a) in scenarios.items()
    ]
