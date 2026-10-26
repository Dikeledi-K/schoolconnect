"""Run the forecast backtest and write the results to docs/forecast_evaluation.md.

Usage:
    python scripts/evaluate_forecast.py                    # forecast from today
    python scripts/evaluate_forecast.py --as-of 2025-12-15 # January-rush demo
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from app import crud  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.forecasting import service  # noqa: E402
from app.forecasting.models import MODEL_DESCRIPTIONS  # noqa: E402

NAMES = {"seasonal_naive": "Same as last week", "last_year": "Same day last year",
         "moving_average": "Recent average", "ml_calendar": "Machine learning"}


def section(bundle, title) -> str:
    summary = service.evaluation_summary(bundle)
    o = summary["overall"]
    lines = [f"## {title}", "",
             f"Forecast start (as of): **{summary['as_of']}**. Backtest window: {o['test_start']} to "
             f"{o['test_end']} ({o['days_tested']} days, 4 rolling 14-day forecasts).", "",
             "| Measure | Value |", "|---|---|",
             f"| Overall error of SchoolConnect forecast (WAPE) | **{o['wape']:.1%}** |",
             f"| Simple 'same as last week' rule (WAPE) | {o['baseline_wape']:.1%} |",
             f"| Improvement over the simple rule | {1 - o['wape'] / o['baseline_wape']:.0%} |",
             f"| Average error per day (MAE, all messages) | ±{o['mae']:.1f} messages |",
             f"| 80% range for the daily total | {o['total_interval'][0]:.2f}× to {o['total_interval'][1]:.2f}× the forecast |",
             "", "WAPE per category and method (lower is better; **bold** = method chosen):", "",
             "| Category | " + " | ".join(NAMES.values()) + " |",
             "|---|" + "---|" * len(NAMES)]
    for c in summary["per_category"]:
        cells = []
        for m in NAMES:
            w = c["models"].get(m, {}).get("wape")
            txt = "n/a" if w is None else f"{w:.0%}"
            cells.append(f"**{txt}**" if m == c["chosen_model"] else txt)
        lines.append(f"| {c['category']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def january_check(bundle) -> str:
    fc = bundle["forecast"]
    total = fc[fc["category"] == "total"].set_index("date")
    act = bundle["actuals"]["total"]
    window = total.loc["2026-01-12":"2026-01-30"]
    a = act.reindex(window.index)
    if a.isna().any():
        return ""
    wape = (window["forecast"] - a).abs().sum() / a.sum()
    inside = ((a >= window["lower"]) & (a <= window["upper"])).mean()
    _, weekly = service.workload(bundle, 45)
    adm = weekly[(weekly["role"] == "admin_clerk") & (weekly["week_start"] == pd.Timestamp("2026-01-19"))]
    lines = ["### January 2026 opening (forecast made on 15 Dec 2025)", "",
             f"- Messages 12–30 Jan: forecast {window['forecast'].sum():.0f}, actual {a.sum():.0f} "
             f"(WAPE {wape:.0%}).",
             f"- Days where the actual total fell inside the 80% range: {inside:.0%}."]
    if len(adm):
        r = adm.iloc[0]
        lines.append(f"- Admin clerk, week of 19 Jan: forecast {r['utilisation']:.0%} of capacity "
                     f"(busy-week scenario {r['utilisation_upper']:.0%}); actual {r['actual_utilisation']:.0%}.")
    lines.append("- The model under-forecasts the peak slightly because it has seen only one previous "
                 "January. Accuracy should improve each year as history grows.")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", default=None)
    args = p.parse_args()
    init_db()
    with SessionLocal() as db:
        rows = crud.ticket_timestamps(db)
    out = ["# Forecast evaluation", "",
           f"_Generated {date.today().isoformat()} by `scripts/evaluate_forecast.py` on the synthetic "
           "demo data. Re-run after regenerating data._", "",
           "Methods:", ""]
    out += [f"- **{NAMES[k]}** (`{k}`): {v}" for k, v in MODEL_DESCRIPTIONS.items()]
    out += ["", "Rule: each category uses its most accurate baseline, and switches to machine learning "
            "only if ML is at least 2% better.", ""]
    live = service.compute_bundle(rows, args.as_of)
    out.append(section(live, "Current forecast"))
    demo = service.compute_bundle(rows, "2025-12-15")
    out.append(section(demo, "Backtest demo: forecasting the January rush"))
    out.append(january_check(demo))
    out.append("## Notes\n\n- Learner welfare has very low daily counts (about 1 a day), so percentage errors "
               "look large even when the forecast is off by only one message. It is planned with a "
               "simple average and always handled by a person.\n- All data is synthetic and the calendar "
               "is approximate (see docs/DATA.md).\n")
    path = ROOT / "docs" / "forecast_evaluation.md"
    path.write_text("\n".join(out))
    print("\n".join(out))
    print(f"Written to {path}")


if __name__ == "__main__":
    main()
