"""Outputs: Excel workbook, PNG charts and a markdown summary."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402

from .model import ScenarioResult  # noqa: E402

COLORS = {"base": "#1F3A5F", "optimistic": "#2E7D32", "stress": "#C62828"}
EUR = '#,##0.00;(#,##0.00);"-"'
PCT = '0.0%;(0.0%);"-"'

# (attribute, label, format) in display order; None attribute = section header
LINES = [
    (None, "LOAN BOOK", None),
    ("opening_loans", "Opening loans", EUR),
    ("originations", "New loans", EUR),
    ("repayments", "Repayments", EUR),
    ("credit_losses", "Credit losses", EUR),
    ("closing_loans", "Closing loans", EUR),
    (None, "BALANCE SHEET", None),
    ("liquidity", "Liquidity", EUR),
    ("other_assets", "Other assets", EUR),
    ("total_assets", "Total assets", EUR),
    ("deposits", "Customer deposits", EUR),
    ("equity_close", "Equity", EUR),
    ("balance_check", "Balance check (must be 0)", EUR),
    (None, "PROFIT AND LOSS", None),
    ("interest_loans", "Interest on loans", EUR),
    ("interest_liquidity", "Interest on liquidity", EUR),
    ("interest_deposits", "Interest paid on deposits", EUR),
    ("nii", "Net interest income", EUR),
    ("fees", "Net fees", EUR),
    ("total_income", "Total income", EUR),
    ("opex", "Operating expenses", EUR),
    ("credit_losses", "Credit losses", EUR),
    ("pbt", "Profit before tax", EUR),
    ("tax", "Tax", EUR),
    ("net_profit", "Net profit", EUR),
    (None, "CAPITAL", None),
    ("rwa", "Risk-weighted assets", EUR),
    ("capital_ratio", "Capital ratio", PCT),
    ("capital_target", "Capital target", PCT),
    ("capital_surplus", "Surplus / (shortfall) vs target", EUR),
    ("leverage_ratio", "Leverage ratio", PCT),
    (None, "KPIs", None),
    ("nim", "Net interest margin", PCT),
    ("cost_income", "Cost / income", PCT),
    ("cost_of_risk_actual", "Cost of risk (actual)", PCT),
    ("roe", "Return on equity", PCT),
    ("loan_to_deposit", "Loans / deposits", PCT),
]


def write_excel(results: list[ScenarioResult], sens: list[dict], path: Path) -> None:
    wb = Workbook()
    hdr_font = Font(name="Arial", bold=True, color="FFFFFF")
    hdr_fill = PatternFill("solid", fgColor="1F3A5F")
    sec_fill = PatternFill("solid", fgColor="DCE6F1")
    base_font = Font(name="Arial")

    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Metric (EUR m)"] + [r.label for r in results])
    for c in ws[1]:
        c.font, c.fill = hdr_font, hdr_fill
    keys = [
        ("loans_end", "Loans, end of year 5", EUR),
        ("deposits_end", "Deposits, end of year 5", EUR),
        ("net_profit_last_year", "Net profit, year 5", EUR),
        ("cumulative_net_profit", "Cumulative net profit, 5 years", EUR),
        ("first_profitable_year", "First profitable year", "0"),
        ("roe_last_year", "ROE, year 5", PCT),
        ("cost_income_last_year", "Cost / income, year 5", PCT),
        ("min_capital_ratio", "Lowest capital ratio", PCT),
        ("max_capital_shortfall", "Largest capital shortfall (negative = short)", EUR),
    ]
    summaries = [r.summary() for r in results]
    for k, label, fmt in keys:
        row = [label] + [s[k] if s[k] is not None else "none" for s in summaries]
        ws.append(row)
        for c in ws[ws.max_row][1:]:
            c.number_format = fmt
    ws.column_dimensions["A"].width = 46
    for col in "BCD":
        ws.column_dimensions[col].width = 14

    # One sheet per scenario
    for r in results:
        ws = wb.create_sheet(r.label)
        ws.append([f"{r.label} scenario (EUR m)"] + [f"Year {y.year}" for y in r.years])
        for c in ws[1]:
            c.font, c.fill = hdr_font, hdr_fill
        for attr, label, fmt in LINES:
            if attr is None:
                ws.append([label])
                for c in ws[ws.max_row]:
                    c.fill = sec_fill
                    c.font = Font(name="Arial", bold=True)
                continue
            ws.append([label] + [getattr(y, attr) for y in r.years])
            for c in ws[ws.max_row][1:]:
                c.number_format = fmt
        ws.column_dimensions["A"].width = 36
        for col in "BCDEF":
            ws.column_dimensions[col].width = 12

    # Sensitivity
    ws = wb.create_sheet("Sensitivity")
    ws.append(["Driver (base case)", "Upside shock", "Downside shock", "Swing"])
    for c in ws[1]:
        c.font, c.fill = hdr_font, hdr_fill
    for s in sens:
        ws.append([s["driver"], s["up"], s["down"], s["swing"]])
        for c in ws[ws.max_row][1:]:
            c.number_format = EUR
    ws.append([])
    ws.append(["Change in cumulative 5-year net profit, EUR m. Up = driver increased, Down = driver decreased."])
    ws.column_dimensions["A"].width = 32
    for col in "BCD":
        ws.column_dimensions[col].width = 15

    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for c in row:
                if not c.font.bold:
                    c.font = base_font
    wb.save(path)


def _style(ax, title: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(0, color="#555555", linewidth=0.8)


def write_charts(results: list[ScenarioResult], sens: list[dict], outdir: Path) -> list[Path]:
    files = []
    years = [y.year for y in results[0].years]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for r in results:
        ax.plot(years, [y.net_profit for y in r.years], marker="o", label=r.label, color=COLORS.get(r.name))
    _style(ax, "Net profit by year: the J-curve", "EUR m")
    ax.set_xticks(years)
    ax.set_xlabel("Year")
    ax.legend(frameon=False)
    files.append(outdir / "net_profit.png")
    fig.tight_layout()
    fig.savefig(files[-1], dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for r in results:
        ax.plot(years, [y.capital_ratio for y in r.years], marker="o", label=r.label, color=COLORS.get(r.name))
    target = results[0].years[0].capital_target
    ax.axhline(target, linestyle="--", color="#888888", label=f"Target {target:.0%}")
    _style(ax, "Capital ratio vs target", "Capital / RWA")
    ax.set_ylim(0, 0.8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xticks(years)
    ax.set_xlabel("Year (year 1 above chart range)")
    ax.legend(frameon=False)
    files.append(outdir / "capital_ratio.png")
    fig.tight_layout()
    fig.savefig(files[-1], dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [s["driver"] for s in sens][::-1]
    ax.barh(labels, [s["up"] for s in sens][::-1], color="#1F3A5F", label="Driver increased")
    ax.barh(labels, [s["down"] for s in sens][::-1], color="#9DB4CF", label="Driver decreased")
    ax.set_title("Sensitivity of cumulative 5-year net profit (base case)", loc="left", fontsize=12, fontweight="bold")
    ax.set_xlabel("Change vs base, EUR m")
    ax.axvline(0, color="#555555", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="lower right")
    files.append(outdir / "sensitivity.png")
    fig.tight_layout()
    fig.savefig(files[-1], dpi=150)
    plt.close(fig)
    return files


def write_markdown(results: list[ScenarioResult], sens: list[dict], path: Path) -> None:
    s = {r.label: r.summary() for r in results}
    labels = list(s)

    def fmt(v, kind):
        if v is None:
            return "none"
        if kind == "pct":
            return f"{v:.1%}"
        if kind == "int":
            return str(v)
        return f"{v:,.1f}"

    rows = [
        ("Loans, end of year 5 (EUR m)", "loans_end", "num"),
        ("Cumulative net profit, 5 years (EUR m)", "cumulative_net_profit", "num"),
        ("First profitable year", "first_profitable_year", "int"),
        ("ROE, year 5", "roe_last_year", "pct"),
        ("Cost / income, year 5", "cost_income_last_year", "pct"),
        ("Lowest capital ratio", "min_capital_ratio", "pct"),
        ("Largest capital shortfall (EUR m)", "max_capital_shortfall", "num"),
    ]
    lines = ["# Results summary", "", "| Metric | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for label, key, kind in rows:
        lines.append(f"| {label} | " + " | ".join(fmt(s[l][key], kind) for l in labels) + " |")
    lines += ["", "## Sensitivity (base case, cumulative 5-year net profit, EUR m)", "",
              "| Driver | Up | Down |", "|---|---|---|"]
    for x in sens:
        lines.append(f"| {x['driver']} | {x['up']:+.1f} | {x['down']:+.1f} |")
    lines += ["", "![Net profit](net_profit.png)", "", "![Capital ratio](capital_ratio.png)", "",
              "![Sensitivity](sensitivity.png)", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
