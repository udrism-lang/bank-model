"""Five-year annual projection for a new digital consumer lender funded by deposits from year 2.

Year 1 is funded by equity. All amounts are in EUR millions.
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
    allowance_coverage: float
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
    op_risk_bic_coefficient: float
    op_risk_ildc_cap: float
    capital_requirement: float
    management_buffer: float


@dataclass
class YearResult:
    year: int
    # Loan book (gross, before the loss allowance)
    opening_gross_loans: float = 0.0
    originations: float = 0.0
    repayments: float = 0.0
    avg_loans: float = 0.0  # average gross loans, before write-offs
    write_offs: float = 0.0
    closing_gross_loans: float = 0.0
    # IFRS 9 loss allowance
    allowance_open: float = 0.0
    allowance_close: float = 0.0
    impairment_charge: float = 0.0  # P&L: write-offs + change in allowance
    closing_loans: float = 0.0  # net: gross minus allowance
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
    interest_earning_assets: float = 0.0
    business_indicator: float = 0.0
    rwa_operational: float = 0.0
    rwa: float = 0.0
    capital_ratio: float = 0.0
    capital_target: float = 0.0
    capital_surplus: float = 0.0
    requirement_surplus: float = 0.0  # vs the minimum requirement, without management buffer
    leverage_ratio: float = 0.0
    # KPIs
    nim: float = 0.0
    cost_income: float = 0.0
    cost_of_risk_actual: float = 0.0  # all-in impairment charge / average gross loans
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
            "cost_of_risk_last_year": last.cost_of_risk_actual,
            "min_capital_ratio": min(y.capital_ratio for y in self.years),
            "max_capital_shortfall": min(y.capital_surplus for y in self.years),
            "max_requirement_shortfall": min(y.requirement_surplus for y in self.years),
        }


def _safe_div(a: float, b: float) -> float:
    return a / b if b > 0 else 0.0


def ildc(net_interest: float, interest_earning_assets: float, cap: float) -> float:
    """Interest, leases and dividend component (CRR Art. 314(2)); no leases or dividends here."""
    return min(abs(net_interest), cap * interest_earning_assets)


def project(a: Assumptions, years: int = 5) -> list[YearResult]:
    """Run the projection. Each year uses only the previous year's results, so there is no circularity."""
    out: list[YearResult] = []
    prev: YearResult | None = None

    for i in range(years):
        y = YearResult(year=i + 1)

        # --- Loan book -------------------------------------------------------
        # Gross book: opening + originations - repayments - write-offs.
        # Write-offs (realised losses) = cost_of_risk x average gross loans.
        y.opening_gross_loans = prev.closing_gross_loans if prev else 0.0
        y.originations = a.originations[i]
        y.repayments = -(y.opening_gross_loans * a.repayment_rate_opening + y.originations * a.repayment_rate_new)
        pre_write_off = y.opening_gross_loans + y.originations + y.repayments
        y.avg_loans = (y.opening_gross_loans + pre_write_off) / 2
        y.write_offs = -y.avg_loans * a.cost_of_risk
        y.closing_gross_loans = pre_write_off + y.write_offs
        # IFRS 9 allowance: 12-month expected loss, a fixed coverage of the closing gross book.
        # The P&L charge is write-offs plus the change in the allowance, so the allowance builds
        # while the book grows (part of the J-curve) and is never counted twice.
        y.allowance_open = prev.allowance_close if prev else 0.0
        y.allowance_close = y.closing_gross_loans * a.allowance_coverage
        y.impairment_charge = y.write_offs - (y.allowance_close - y.allowance_open)
        y.closing_loans = y.closing_gross_loans - y.allowance_close

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
        y.pbt = y.total_income + y.opex + y.impairment_charge
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
        # Operational risk, CRR3 business indicator (Art. 312-314): BI = ILDC + services + financial.
        # ILDC = min(|interest income - interest expense|, cap x interest-earning assets), on 3-year
        # averages; services = fee income; financial component = 0 (no trading book). With BI below
        # EUR 1bn the own funds requirement is 12% x BI, and RWA = 12.5 x requirement.
        y.interest_earning_assets = y.closing_loans + y.liquidity
        window = (out + [y])[-3:]  # up to three years; fewer in years 1-2 (new bank)
        n = len(window)
        avg_ni = sum(z.interest_loans + z.interest_liquidity + z.interest_deposits for z in window) / n
        avg_iea = sum(z.interest_earning_assets for z in window) / n
        avg_fees = sum(max(0.0, z.fees) for z in window) / n
        y.business_indicator = ildc(avg_ni, avg_iea, a.op_risk_ildc_cap) + avg_fees
        y.rwa_operational = 12.5 * a.op_risk_bic_coefficient * y.business_indicator
        y.rwa = y.rwa_credit + y.rwa_other + y.rwa_operational
        y.capital_ratio = _safe_div(y.equity_close, y.rwa)
        y.capital_target = a.capital_requirement + a.management_buffer
        y.capital_surplus = y.equity_close - y.capital_target * y.rwa
        y.requirement_surplus = y.equity_close - a.capital_requirement * y.rwa
        y.leverage_ratio = _safe_div(y.equity_close, y.total_assets)

        # --- KPIs ------------------------------------------------------------
        avg_assets = (prev.total_assets + y.total_assets) / 2 if prev else y.total_assets / 2
        y.nim = _safe_div(y.nii, avg_assets)
        y.cost_income = _safe_div(-y.opex, y.total_income)
        y.cost_of_risk_actual = _safe_div(-y.impairment_charge, y.avg_loans)
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
