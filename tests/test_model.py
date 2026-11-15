"""Tests: roll-forwards and liquidity hold, credit-loss and op-risk logic behave as documented,
and key outputs match reference values (regression)."""
from dataclasses import replace
from pathlib import Path

import pytest

from bankmodel.model import ildc, project, run_all

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def results():
    return {r.name: r for r in run_all(ROOT / "assumptions.yaml")}


def test_balance_sheet_balances_every_year(results):
    # Holds by construction (liquidity is the plug), so this only guards against coding slips.
    for r in results.values():
        for y in r.years:
            assert y.balance_check == pytest.approx(0, abs=1e-9), f"{r.name} year {y.year}"


def test_gross_loan_roll_forward(results):
    for r in results.values():
        for y in r.years:
            assert y.closing_gross_loans == pytest.approx(
                y.opening_gross_loans + y.originations + y.repayments + y.write_offs
            )


def test_allowance_roll_forward(results):
    for r in results.values():
        prev_close = 0.0
        for y in r.years:
            assert y.allowance_open == pytest.approx(prev_close)
            # Net loans = gross - allowance; charge = write-offs + allowance build
            assert y.closing_loans == pytest.approx(y.closing_gross_loans - y.allowance_close)
            assert -y.impairment_charge == pytest.approx(-y.write_offs + y.allowance_close - y.allowance_open)
            prev_close = y.allowance_close


def test_impairment_rate_is_write_offs_plus_allowance_build(results):
    for r in results.values():
        a = r.assumptions
        for y in r.years:
            build = (y.allowance_close - y.allowance_open) / y.avg_loans
            assert y.cost_of_risk_actual == pytest.approx(a.cost_of_risk + build)
            # The book grows, so the all-in rate sits above the write-off rate, but the
            # allowance can never add more than its coverage of the closing book.
            assert a.cost_of_risk <= y.cost_of_risk_actual
            assert build <= a.allowance_coverage * y.closing_gross_loans / y.avg_loans


def test_no_double_counting_in_steady_state(results):
    # With a flat book the allowance stops building and the charge equals write-offs.
    a = results["base"].assumptions
    flat = replace(a, originations=[100.0] * 30, fixed_opex=[5.0] * 30)
    last = project(flat, 30)[-1]
    assert last.cost_of_risk_actual == pytest.approx(a.cost_of_risk, abs=1e-4)


def test_equity_roll_forward(results):
    for r in results.values():
        for y in r.years:
            assert y.equity_close == pytest.approx(y.equity_open + y.capital_injection + y.net_profit)


def test_liquidity_never_negative(results):
    for r in results.values():
        assert all(y.liquidity >= 0 for y in r.years), r.name


def test_ildc_cap():
    assert ildc(10.0, 100.0, 0.0225) == pytest.approx(2.25)  # cap binds
    assert ildc(-1.0, 100.0, 0.0225) == pytest.approx(1.0)  # absolute value, below cap
    assert ildc(2.0, 100.0, 0.0225) == pytest.approx(2.0)


def test_op_risk_rwa_follows_business_indicator(results):
    for r in results.values():
        a = r.assumptions
        for i, y in enumerate(r.years):
            window = r.years[max(0, i - 2): i + 1]
            n = len(window)
            ni = sum(z.interest_loans + z.interest_liquidity + z.interest_deposits for z in window) / n
            iea = sum(z.interest_earning_assets for z in window) / n
            fees = sum(z.fees for z in window) / n
            bi = min(abs(ni), a.op_risk_ildc_cap * iea) + fees
            assert y.business_indicator == pytest.approx(bi)
            assert y.rwa_operational == pytest.approx(12.5 * a.op_risk_bic_coefficient * bi)


def test_reference_values(results):
    """Regression values from the current model. Update deliberately if the logic changes."""
    expected = {
        # scenario: (net loans Y5, PBT Y5, surplus vs target Y5, cumulative net profit, first profit year)
        "base": (199.184, 2.432, -3.140, -5.707, 5),
        "optimistic": (241.200, 8.452, 3.131, 6.228, 3),
        "stress": (135.002, -6.404, -14.920, -26.081, None),
    }
    for name, (loans, pbt, surplus, cum, first) in expected.items():
        r = results[name]
        y5 = r.years[-1]
        assert y5.closing_loans == pytest.approx(loans, abs=0.001), name
        assert y5.pbt == pytest.approx(pbt, abs=0.001), name
        assert y5.capital_surplus == pytest.approx(surplus, abs=0.001), name
        assert r.summary()["cumulative_net_profit"] == pytest.approx(cum, abs=0.001), name
        assert r.first_profitable_year() == first, name


def test_no_tax_while_losses_not_recovered(results):
    for y in results["base"].years:
        if y.cumulative_pbt <= 0:
            assert y.tax == 0


def test_capital_injection_closes_shortfall(results):
    a = results["base"].assumptions
    assert min(y.capital_surplus for y in project(replace(a, capital_injection_year3=2.5))) < 0
    assert min(y.capital_surplus for y in project(replace(a, capital_injection_year3=3.5))) > 0


def test_higher_cost_of_risk_reduces_profit(results):
    a = results["base"].assumptions
    base_profit = sum(y.net_profit for y in project(a))
    worse = sum(y.net_profit for y in project(replace(a, cost_of_risk=a.cost_of_risk + 0.01)))
    assert worse < base_profit
