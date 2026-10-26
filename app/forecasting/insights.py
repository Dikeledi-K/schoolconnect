"""Plain-language recommendations built ONLY from computed numbers.

The text comes from fixed templates, so it can never invent facts, dates or numbers.
No personal data is involved: insights are built from aggregate counts only.
"""

import pandas as pd

from app.forecasting.workload import category_mix
from app.taxonomy import CATEGORIES, STAFF_ROLES

ACTIONS = {
    "admissions": "publish an admissions FAQ and document checklist on the school website and "
                  "WhatsApp groups before the rush, and consider a temporary admin assistant",
    "fees_exemptions": "send fee statements and exemption application forms to parents proactively "
                       "at the start of the month",
    "academic": "share exam timetables and report collection dates with parents in advance",
    "learner_welfare": "block time in the deputy principal's diary; welfare cases must always be "
                       "handled by a person",
    "transport": "send scholar transport routes and times to parents before term starts",
    "it_portal": "post a step-by-step portal guide and check the portal can handle the load",
    "other": "add the most common questions to a parent FAQ",
}


def _fmt_date(d) -> str:
    return f"{pd.Timestamp(d).day} {pd.Timestamp(d):%b %Y}"


def build_insights(forecast: pd.DataFrame, weekly: pd.DataFrame, surges: list[dict],
                   last_year_total: float | None, days: int) -> list[dict]:
    insights = []
    total = forecast[forecast["category"] == "total"]["forecast"].sum()
    text = f"About {total:.0f} parent messages are expected in the next {days} days."
    if last_year_total:
        change = (total - last_year_total) / last_year_total * 100
        if abs(change) < 1:
            text += " That is about the same as the same period last year."
        else:
            text += f" That is {abs(change):.0f}% {'more' if change > 0 else 'fewer'} than the same period last year."
    insights.append({"type": "summary", "severity": "info", "text": text})

    # One insight per role: its most loaded week (keeps the list short enough to act on).
    seen_roles = set()
    for _, w in weekly.sort_values("utilisation", ascending=False).iterrows():
        if w["status"] not in ("overloaded", "busy") and not w.get("overload_risk", False):
            continue
        if w["role"] in seen_roles:
            continue
        seen_roles.add(w["role"])
        week_end = w["week_start"] + pd.Timedelta(days=6)
        mix = category_mix(forecast, w["role"], w["week_start"], week_end)
        top_cat = mix[0][0] if mix else None
        top_name = CATEGORIES[top_cat].display_name.lower() if top_cat else "general"
        pct = w["utilisation"] * 100
        if w["status"] == "overloaded":
            extra = w["hours_needed"] - w["capacity_hours"]
            msg = (f"{w['role_name']} is forecast at {pct:.0f}% capacity in the week of "
                   f"{_fmt_date(w['week_start'])}, mainly {top_name} queries. That is about "
                   f"{extra:.0f} hours more work than available. Suggested action: {ACTIONS.get(top_cat, 'plan extra help')}.")
            severity = "high"
        elif w["status"] == "busy":
            msg = (f"{w['role_name']} will be busy ({pct:.0f}% capacity) in the week of "
                   f"{_fmt_date(w['week_start'])}, mainly {top_name} queries. Plan ahead: {ACTIONS.get(top_cat, 'monitor')}.")
            severity = "medium"
        else:
            msg = (f"{w['role_name']} is expected to cope in the week of {_fmt_date(w['week_start'])} "
                   f"({pct:.0f}% capacity), but a busy week could push this to "
                   f"{w['utilisation_upper'] * 100:.0f}%, mainly {top_name} queries. Have a back-up plan: "
                   f"{ACTIONS.get(top_cat, 'monitor')}.")
            severity = "low"
        if w["status"] == "busy" and w.get("overload_risk", False):
            msg += f" In a busy week it could reach {w['utilisation_upper'] * 100:.0f}%."
        insights.append({"type": "workload", "severity": severity, "role": w["role"],
                         "week_start": w["week_start"].date().isoformat(), "text": msg})

    if surges:
        top = max(surges, key=lambda s: s["ratio"])
        insights.append({
            "type": "surge", "severity": "medium", "date": top["date"],
            "text": (f"Biggest expected spike: {_fmt_date(top['date'])}, about {top['expected_tickets']:.0f} "
                     f"messages ({top['ratio']:.1f}x a normal day), driven by {', '.join(top['drivers'])}. "
                     f"Most will be {top['main_category_name'].lower()} queries for the "
                     f"{STAFF_ROLES[top['routes_to']].lower()}."),
        })

    if not any(i["type"] == "workload" for i in insights):
        insights.insert(1, {"type": "workload", "severity": "info",
                            "text": "All staff roles are forecast to stay within capacity, even in a busy "
                                    "week. No extra help is needed for this period."})
    return insights
