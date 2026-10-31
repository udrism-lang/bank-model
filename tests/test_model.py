"""Tests: accounting identities hold, and results match the companion Excel workbook."""
from dataclasses import replace
from pathlib import Path

import pytest

from bankmodel.model import project, run_all

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def results():
    return {r.name: r for r in run_all(ROOT / "assumptions.yaml")}


def test_balance_sheet_balances_every_year(results):
    for r in results.values():
        for y in r.years:
            assert y.balance_check == pytest.approx(0, abs=1e-9), f"{r.name} year {y.year}"


def test_loan_roll_forward(results):
    for r in results.values():
        for y in r.years:
            assert y.closing_loans == pytest.approx(y.opening_loans + y.originations + y.repayments + y.credit_losses)


def test_equity_roll_forward(results):
    for r in results.values():
        for y in r.years:
            assert y.equity_close == pytest.approx(y.equity_open + y.capital_injection + y.net_profit)


def test_liquidity_never_negative(results):
    for r in results.values():
        assert all(y.liquidity >= 0 for y in r.years), r.name


def test_matches_excel_base_case(results):
    """Reference values from Banka_X_finansu_modelis.xlsx, sheet Modelis_Baze (recalculated)."""
    base = results["base"]
    y5 = base.years[-1]
    assert y5.closing_loans == pytest.approx(198.805, abs=0.001)
    assert y5.pbt == pytest.approx(1.59, abs=0.01)
    assert y5.capital_surplus == pytest.approx(-7.745, abs=0.01)
    assert base.first_profitable_year() == 5


def test_no_tax_while_losses_not_recovered(results):
    for y in results["base"].years:
        if y.cumulative_pbt <= 0:
            assert y.tax == 0


def test_capital_injection_closes_shortfall(results):
    a = results["base"].assumptions
    years = project(replace(a, capital_injection_year3=8.0))
    assert min(y.capital_surplus for y in years) > 0


def test_higher_cost_of_risk_reduces_profit(results):
    a = results["base"].assumptions
    base_profit = sum(y.net_profit for y in project(a))
    worse = sum(y.net_profit for y in project(replace(a, cost_of_risk=a.cost_of_risk + 0.01)))
    assert worse < base_profit
