"""Parity: docs/calculator/model.js must compute what bankmodel/model.py computes.

Runs model.js under Node for the three scenarios and a set of perturbed inputs, and compares
every yearly field and every summary value with Python to 1e-9 relative. Skipped if `node`
is not on PATH.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import asdict, fields, replace
from pathlib import Path

import pytest

from bankmodel.model import ScenarioResult, YearResult, load_scenarios, project

ROOT = Path(__file__).resolve().parents[1]
MODEL_JS = ROOT / "docs" / "calculator" / "model.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not on PATH")

RUNNER = r"""
const fs = require("fs");
const model = require(process.argv[2]);
const cases = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = cases.map(c => {
  const years = model.project(c.inputs, c.years);
  return { name: c.name, years, summary: model.summary(years) };
});
process.stdout.write(JSON.stringify(out));
"""

REL = 1e-9
ABS = 1e-12  # for values that are zero in exact arithmetic


def _cases():
    years, scenarios = load_scenarios(ROOT / "assumptions.yaml")
    base = scenarios["base"][1]
    opt = scenarios["optimistic"][1]
    stress = scenarios["stress"][1]
    cases = [(key, a) for key, (_, a) in scenarios.items()]
    cases += [
        ("base_high_write_offs", replace(base, cost_of_risk=0.045)),
        ("base_low_yield", replace(base, loan_yield=0.085)),
        ("base_more_capital", replace(base, initial_capital=45.0)),
        ("base_less_capital", replace(base, initial_capital=12.0)),
        ("base_injection_y3", replace(base, capital_injection_year3=3.5)),
        ("base_expensive_funding", replace(base, deposit_rate=0.045, liquidity_ratio=0.35)),
        ("base_costly", replace(base, allowance_coverage=0.03, fee_rate=0.0, cac_rate=0.055)),
        ("base_requirement", replace(base, capital_requirement=0.12, management_buffer=0.035)),
        (
            "optimistic_scaled",
            replace(opt, originations=[v * 1.3 for v in opt.originations],
                    fixed_opex=[v * 0.8 for v in opt.fixed_opex]),
        ),
        (
            "stress_scaled_down",
            replace(stress, originations=[v * 0.55 for v in stress.originations],
                    fixed_opex=[v * 1.25 for v in stress.fixed_opex]),
        ),
        ("base_no_deposits_needed", replace(base, initial_capital=300.0)),  # deposits floor at zero
        ("base_ildc_cap_binds", replace(base, loan_yield=0.17, op_risk_ildc_cap=0.01)),
    ]
    return years, cases


def _close(js, py) -> bool:
    if py is None or js is None:
        return py is None and js is None
    return math.isclose(js, py, rel_tol=REL, abs_tol=ABS)


@pytest.fixture(scope="module")
def parity():
    years, cases = _cases()
    payload = [{"name": n, "years": years, "inputs": asdict(a)} for n, a in cases]
    tmp = ROOT / ".pytest_cache" / "web_parity"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "runner.js").write_text(RUNNER, encoding="utf-8")
    (tmp / "cases.json").write_text(json.dumps(payload), encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(tmp / "runner.js"), str(MODEL_JS), str(tmp / "cases.json")],
        capture_output=True, text=True, check=True, timeout=60,
    )
    js = {r["name"]: r for r in json.loads(proc.stdout)}
    py = {}
    for name, a in cases:
        r = ScenarioResult(name=name, label=name, assumptions=a, years=project(a, years))
        py[name] = r
    return cases, js, py


def test_cases_cover_both_branches(parity):
    _, _, py = parity
    # The deposit floor and the ILDC cap should each be exercised by at least one case.
    assert any(y.deposits == 0 for y in py["base_no_deposits_needed"].years)
    r = py["base_ildc_cap_binds"]
    window = r.years[-3:]
    avg_ni = sum(z.nii for z in window) / 3
    avg_iea = sum(z.interest_earning_assets for z in window) / 3
    assert abs(avg_ni) > r.assumptions.op_risk_ildc_cap * avg_iea


def test_every_yearly_field_matches(parity):
    cases, js, py = parity
    names = [f.name for f in fields(YearResult)]
    mismatches = []
    for name, _ in cases:
        assert len(js[name]["years"]) == len(py[name].years), name
        for jy, pyy in zip(js[name]["years"], py[name].years):
            for field_name in names:
                pv = getattr(pyy, field_name)
                jv = jy.get(field_name)
                if not _close(jv, pv):
                    mismatches.append(f"{name} Y{pyy.year} {field_name}: js={jv!r} py={pv!r}")
    assert not mismatches, "\n".join(mismatches[:30])


def test_summary_matches(parity):
    cases, js, py = parity
    mismatches = []
    for name, _ in cases:
        ps = py[name].summary()
        jsum = js[name]["summary"]
        assert set(jsum) == set(ps), name
        for key, pv in ps.items():
            if not _close(jsum[key], pv):
                mismatches.append(f"{name} {key}: js={jsum[key]!r} py={pv!r}")
    assert not mismatches, "\n".join(mismatches)


def test_base_case_headline_values(parity):
    # The figures quoted in the README, computed by model.js.
    _, js, _ = parity
    s = js["base"]["summary"]
    assert s["first_profitable_year"] == 5
    assert round(s["cumulative_net_profit"], 1) == -5.7
    assert round(s["roe_last_year"] * 100, 1) == 10.5
    assert round(s["min_capital_ratio"] * 100, 1) == 15.1
    assert round(s["max_capital_shortfall"], 1) == -3.1
