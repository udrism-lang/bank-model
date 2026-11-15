"""Export assumptions.yaml for the web calculator.

Writes docs/calculator/assumptions.json and refreshes the fallback copy embedded in
docs/calculator/index.html (used when the page is opened from disk and fetch() is blocked).
Run after any change to assumptions.yaml:

    python tools/export_web_assumptions.py

tests/test_web_assumptions.py fails if either copy drifts from the YAML.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bankmodel.model import load_scenarios  # noqa: E402

YAML_PATH = ROOT / "assumptions.yaml"
JSON_PATH = ROOT / "docs" / "calculator" / "assumptions.json"
HTML_PATH = ROOT / "docs" / "calculator" / "index.html"
FALLBACK_RE = re.compile(
    r'(<script type="application/json" id="assumptions-fallback">)(.*?)(</script>)', re.DOTALL
)


def build(yaml_path: Path = YAML_PATH) -> dict:
    """The JSON document: scenario inputs exactly as the Python model loads them, plus labels."""
    years, scenarios = load_scenarios(yaml_path)
    cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return {
        "generated_from": "assumptions.yaml by tools/export_web_assumptions.py (do not edit by hand)",
        "years": years,
        "scenarios": {
            key: {"label": label, "inputs": asdict(a)} for key, (label, a) in scenarios.items()
        },
        "descriptions": {
            name: {"description": spec.get("description", ""), "unit": spec.get("unit", "")}
            for name, spec in cfg["assumptions"].items()
        },
    }


def embedded_json(data: dict) -> str:
    # Compact, and safe inside a <script> element.
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def read_embedded(html: str) -> dict:
    m = FALLBACK_RE.search(html)
    if not m:
        raise ValueError("fallback <script id=assumptions-fallback> not found in index.html")
    return json.loads(m.group(2))


def main() -> None:
    data = build()
    JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    html = HTML_PATH.read_text(encoding="utf-8")
    if not FALLBACK_RE.search(html):
        raise SystemExit("fallback <script id=assumptions-fallback> not found in index.html")
    html = FALLBACK_RE.sub(lambda m: m.group(1) + embedded_json(data) + m.group(3), html, count=1)
    HTML_PATH.write_text(html, encoding="utf-8", newline="\n")
    print(f"Wrote {JSON_PATH.relative_to(ROOT)} and refreshed the fallback in {HTML_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
