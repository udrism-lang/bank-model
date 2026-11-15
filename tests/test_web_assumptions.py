"""The web calculator's assumptions (JSON file and the fallback embedded in index.html) must match
assumptions.yaml. If this fails, run: python tools/export_web_assumptions.py"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from export_web_assumptions import HTML_PATH, JSON_PATH, build, read_embedded  # noqa: E402

from bankmodel.model import load_scenarios  # noqa: E402

HINT = "out of date: run python tools/export_web_assumptions.py"


def test_json_matches_yaml():
    assert json.loads(JSON_PATH.read_text(encoding="utf-8")) == build(), f"assumptions.json {HINT}"


def test_embedded_fallback_matches_yaml():
    assert read_embedded(HTML_PATH.read_text(encoding="utf-8")) == build(), f"index.html fallback {HINT}"


def test_json_inputs_equal_python_inputs():
    # Independent of build(): every scenario input the Python model uses is in the JSON, unchanged.
    years, scenarios = load_scenarios(ROOT / "assumptions.yaml")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    assert data["years"] == years
    assert set(data["scenarios"]) == set(scenarios)
    for key, (label, a) in scenarios.items():
        assert data["scenarios"][key]["label"] == label
        assert data["scenarios"][key]["inputs"] == asdict(a)
