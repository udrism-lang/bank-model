/*
 * Line-by-line JavaScript port of bankmodel/model.py (project() and ScenarioResult.summary()).
 *
 * bankmodel/model.py is the source of truth. tests/test_web_parity.py runs this file under Node
 * and checks every yearly field against Python to 1e-9 relative. If you change the Python model,
 * change this file the same way and run the tests.
 *
 * UMD: in the browser it defines window.BankModel; in Node, module.exports.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.BankModel = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Python 3.12+ built-in sum() over floats uses Neumaier compensated summation.
  // Reproduce it so sums match Python bit for bit, not just approximately.
  function pySum(values) {
    var f = 0.0;
    var c = 0.0;
    for (var k = 0; k < values.length; k++) {
      var x = values[k];
      var t = f + x;
      if (Math.abs(f) >= Math.abs(x)) {
        c += (f - t) + x;
      } else {
        c += (x - t) + f;
      }
      f = t;
    }
    if (c && isFinite(c)) {
      f += c;
    }
    return f;
  }

  function safeDiv(a, b) {
    return b > 0 ? a / b : 0.0;
  }

  // Interest, leases and dividend component (CRR Art. 314(2)); no leases or dividends here.
  function ildc(netInterest, interestEarningAssets, cap) {
    return Math.min(Math.abs(netInterest), cap * interestEarningAssets);
  }

  // Run the projection. Each year uses only the previous year's results, so there is no circularity.
  function project(a, years) {
    if (years === undefined) years = 5;
    var out = [];
    var prev = null;

    for (var i = 0; i < years; i++) {
      var y = { year: i + 1 };

      // --- Loan book ---------------------------------------------------------
      y.opening_gross_loans = prev ? prev.closing_gross_loans : 0.0;
      y.originations = a.originations[i];
      y.repayments = -(y.opening_gross_loans * a.repayment_rate_opening + y.originations * a.repayment_rate_new);
      var preWriteOff = y.opening_gross_loans + y.originations + y.repayments;
      y.avg_loans = (y.opening_gross_loans + preWriteOff) / 2;
      y.write_offs = -y.avg_loans * a.cost_of_risk;
      y.closing_gross_loans = preWriteOff + y.write_offs;
      // IFRS 9 allowance: fixed coverage of the closing gross book.
      y.allowance_open = prev ? prev.allowance_close : 0.0;
      y.allowance_close = y.closing_gross_loans * a.allowance_coverage;
      y.impairment_charge = y.write_offs - (y.allowance_close - y.allowance_open);
      y.closing_loans = y.closing_gross_loans - y.allowance_close;

      // --- Funding -----------------------------------------------------------
      y.other_assets = a.other_assets;
      y.equity_open = prev === null ? a.initial_capital : prev.equity_close;
      y.capital_injection = y.year === 3 ? a.capital_injection_year3 : 0.0;
      var lossAdj = prev ? Math.min(0.0, prev.net_profit) : 0.0;
      y.deposits = Math.max((y.closing_loans + y.other_assets - y.equity_open - lossAdj) / (1 - a.liquidity_ratio), 0.0);
      y.liquidity_pre_profit = y.deposits + y.equity_open + y.capital_injection - y.closing_loans - y.other_assets;

      // --- P&L ---------------------------------------------------------------
      y.interest_loans = y.avg_loans * a.loan_yield;
      var prevLiq = prev ? prev.liquidity : 0.0;
      y.interest_liquidity = (prevLiq + y.liquidity_pre_profit) / 2 * a.liquidity_yield;
      var prevDep = prev ? prev.deposits : 0.0;
      y.interest_deposits = -(prevDep + y.deposits) / 2 * a.deposit_rate;
      y.nii = y.interest_loans + y.interest_liquidity + y.interest_deposits;
      y.fees = y.avg_loans * a.fee_rate;
      y.total_income = y.nii + y.fees;
      y.fixed_opex = -a.fixed_opex[i];
      y.acquisition_cost = -y.originations * a.cac_rate;
      y.servicing_cost = -y.avg_loans * a.servicing_rate;
      y.opex = y.fixed_opex + y.acquisition_cost + y.servicing_cost;
      y.pbt = y.total_income + y.opex + y.impairment_charge;
      y.cumulative_pbt = (prev ? prev.cumulative_pbt : 0.0) + y.pbt;
      y.tax = -Math.max(0.0, Math.min(y.pbt, y.cumulative_pbt)) * a.tax_rate; // simple loss carry-forward
      y.net_profit = y.pbt + y.tax;

      // --- Capital and balance sheet close -----------------------------------
      y.equity_close = y.equity_open + y.capital_injection + y.net_profit;
      y.liquidity = y.deposits + y.equity_close - y.closing_loans - y.other_assets;
      y.total_assets = y.closing_loans + y.liquidity + y.other_assets;
      y.total_liabilities_equity = y.deposits + y.equity_close;

      y.rwa_credit = y.closing_loans * a.risk_weight_loans;
      y.rwa_other = y.other_assets;
      // Operational risk, CRR3 business indicator on 3-year averages (fewer in years 1-2).
      y.interest_earning_assets = y.closing_loans + y.liquidity;
      var window = out.concat([y]).slice(-3);
      var n = window.length;
      var avgNi = pySum(window.map(function (z) { return z.interest_loans + z.interest_liquidity + z.interest_deposits; })) / n;
      var avgIea = pySum(window.map(function (z) { return z.interest_earning_assets; })) / n;
      var avgFees = pySum(window.map(function (z) { return Math.max(0.0, z.fees); })) / n;
      y.business_indicator = ildc(avgNi, avgIea, a.op_risk_ildc_cap) + avgFees;
      y.rwa_operational = 12.5 * a.op_risk_bic_coefficient * y.business_indicator;
      y.rwa = y.rwa_credit + y.rwa_other + y.rwa_operational;
      y.capital_ratio = safeDiv(y.equity_close, y.rwa);
      y.capital_target = a.capital_requirement + a.management_buffer;
      y.capital_surplus = y.equity_close - y.capital_target * y.rwa;
      y.requirement_surplus = y.equity_close - a.capital_requirement * y.rwa;
      y.leverage_ratio = safeDiv(y.equity_close, y.total_assets);

      // --- KPIs --------------------------------------------------------------
      var avgAssets = prev ? (prev.total_assets + y.total_assets) / 2 : y.total_assets / 2;
      y.nim = safeDiv(y.nii, avgAssets);
      y.cost_income = safeDiv(-y.opex, y.total_income);
      y.cost_of_risk_actual = safeDiv(-y.impairment_charge, y.avg_loans);
      y.roe = safeDiv(y.net_profit, (y.equity_open + y.equity_close) / 2);
      y.loan_to_deposit = safeDiv(y.closing_loans, y.deposits);

      out.push(y);
      prev = y;
    }
    return out;
  }

  function firstProfitableYear(years) {
    for (var k = 0; k < years.length; k++) {
      if (years[k].net_profit > 0) return years[k].year;
    }
    return null;
  }

  function minOf(values) {
    return values.reduce(function (m, v) { return v < m ? v : m; });
  }

  // Same keys as ScenarioResult.summary() in Python.
  function summary(years) {
    var last = years[years.length - 1];
    return {
      loans_end: last.closing_loans,
      deposits_end: last.deposits,
      total_assets_end: last.total_assets,
      net_profit_last_year: last.net_profit,
      cumulative_net_profit: pySum(years.map(function (y) { return y.net_profit; })),
      first_profitable_year: firstProfitableYear(years),
      roe_last_year: last.roe,
      cost_income_last_year: last.cost_income,
      nim_last_year: last.nim,
      cost_of_risk_last_year: last.cost_of_risk_actual,
      min_capital_ratio: minOf(years.map(function (y) { return y.capital_ratio; })),
      max_capital_shortfall: minOf(years.map(function (y) { return y.capital_surplus; })),
      max_requirement_shortfall: minOf(years.map(function (y) { return y.requirement_surplus; }))
    };
  }

  return {
    project: project,
    summary: summary,
    firstProfitableYear: firstProfitableYear,
    ildc: ildc,
    pySum: pySum
  };
});
