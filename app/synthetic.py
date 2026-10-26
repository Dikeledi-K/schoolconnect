"""Synthetic ticket history for demos and tests.

All data here is SYNTHETIC. No real parents, learners or messages are used.
The daily rate for each category is built from the school calendar so that the
history contains the patterns a real school office sees (see docs/DATA.md).
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.forecasting.data import SCHOOL_TIMEZONE
from app.forecasting.calendar import calendar_features
from app.taxonomy import CATEGORIES, GRADES

TZ = ZoneInfo(SCHOOL_TIMEZONE)

# Average tickets per school day (Wednesday, mid-term, before growth).
BASE_RATES = {
    "admissions": 2.0,
    "fees_exemptions": 3.0,
    "academic": 4.0,
    "learner_welfare": 0.8,
    "transport": 1.5,
    "it_portal": 1.5,
    "other": 2.0,
}
WEEKDAY_FACTOR = [1.30, 1.10, 1.00, 0.95, 0.80, 0.08, 0.05]  # Mon..Sun
ANNUAL_GROWTH = 0.10

# One-off events that a calendar cannot predict (the models should NOT learn them).
SHOCKS = {
    ("2025-07-23", "it_portal"): 8.0,   # online admissions portal crashed on opening day
    ("2025-03-10", "transport"): 6.0,   # scholar transport strike
    ("2026-05-12", "it_portal"): 5.0,   # school app outage
}

TEMPLATES = {
    "admissions": {
        "en": ["Good day, I applied for Grade {g} for my child and still have no placement. Please help.",
               "Hi, is there still space for Grade {g}? We moved to the area last month.",
               "What documents do I need for the admission application? Birth certificate and proof of address?",
               "My child is on the waiting list for Grade {g}, how long will it take?",
               "I want to transfer my child to your school for next year, how do I apply?"],
        "zu": ["Sawubona, ngicela ukwazi ngokubhalisa umntwana wami ku-Grade {g}."],
        "af": ["Goeie dag, ek het aansoek gedoen vir graad {g} maar het nog nie gehoor nie."],
        "st": ["Dumela, ke kopa ho tseba ka ho ngodisa ngwana sekolong bakeng sa grade {g}."],
    },
    "fees_exemptions": {
        "en": ["Please send me the school fees statement for my child in Grade {g}.",
               "I paid the fees last week but it is not reflecting. Here is the receipt.",
               "How do I apply for a fee exemption? I lost my job this year.",
               "Can I pay the fees in instalments? The balance is too high this month.",
               "Why is there still a balance on my statement? I have a debit order."],
        "zu": ["Sawubona, ngicela usizo nge-imali yesikole, angikwazi ukukhokha yonke."],
        "af": ["Goeie dag, ek wil asseblief aansoek doen vir vrystelling van skoolgeld."],
        "xh": ["Molo, ndicela ukwazi ngemali yesikolo ka-grade {g}."],
    },
    "academic": {
        "en": ["When will the Grade {g} report cards be available?",
               "My child says she is failing maths, can I meet the teacher?",
               "What is the exam timetable for Grade {g}?",
               "My son did not get his homework marked, who can I speak to?",
               "Can we discuss subject choices for Grade {g} next year?"],
        "zu": ["Sawubona, ngicela ukwazi imiphumela yezivivinyo zika-Grade {g}."],
        "af": ["Goeie dag, wanneer kry ons die rapport vir graad {g}?"],
    },
    "learner_welfare": {
        "en": ["My child is being bullied by older learners on the way home. Please help.",
               "My daughter came home hurt after a fight at school today.",
               "My son is very unhappy at school and does not want to go anymore.",
               "Can my child see the school counsellor? She is struggling after a death in the family."],
        "zu": ["Umntwana wami uyahlukunyezwa ngabanye abafundi esikoleni."],
        "af": ["My kind word geboelie by die skool, ek is baie bekommerd."],
    },
    "transport": {
        "en": ["The scholar transport bus did not come this morning.",
               "Which taxi route goes past the school for Grade {g} learners?",
               "The bus is always late in the afternoon, my child waits for an hour.",
               "Can my child be added to the scholar transport list?"],
        "zu": ["Ibhasi yesikole ayifikanga namhlanje ekuseni."],
    },
    "it_portal": {
        "en": ["The online admissions portal keeps giving an error when I upload documents.",
               "I forgot my password for the school app, how do I reset it?",
               "I am not receiving the OTP to log in to the portal.",
               "The website is down, I cannot see the application status."],
        "af": ["Die webwerf werk nie, ek kan nie aanteken nie."],
    },
    "other": {
        "en": ["Where can I buy the school uniform?",
               "Is there a parents meeting this week?",
               "My child lost his jersey, is there lost property?",
               "What time does the sports day start on Saturday?"],
    },
}
LANGUAGE_MIX = {"en": 0.70, "zu": 0.12, "af": 0.08, "st": 0.05, "xh": 0.05}
URGENCY_MIX = {
    "admissions": {"low": 0.2, "medium": 0.6, "high": 0.2},
    "fees_exemptions": {"low": 0.3, "medium": 0.55, "high": 0.15},
    "academic": {"low": 0.6, "medium": 0.3, "high": 0.1},
    "learner_welfare": {"high": 0.8, "critical": 0.2},
    "transport": {"low": 0.3, "medium": 0.3, "high": 0.4},
    "it_portal": {"low": 0.4, "medium": 0.4, "high": 0.2},
    "other": {"low": 0.9, "medium": 0.1},
}
CHANNELS = ["web", "web", "whatsapp", "email"]


def expected_rates(start, end) -> pd.DataFrame:
    """Expected (mean) tickets per day per category. Index = date."""
    cal = calendar_features(start, end)
    years = (cal.index - cal.index[0]).days / 365.25
    growth = (1 + ANNUAL_GROWTH) ** years
    dow = np.array(WEEKDAY_FACTOR)[cal["day_of_week"].to_numpy()]

    # Holidays are quiet, except the office gets calls in the week before term.
    season = np.where(cal["is_holiday_break"] == 1, 0.15, 1.0)
    season = np.where(cal["pre_term_week"] == 1, 0.8, season)
    season = np.where(cal["is_public_holiday"] == 1, 0.05, season)
    january = (cal.index.month == 1).astype(float)

    rates = pd.DataFrame(index=cal.index)
    for cat, base in BASE_RATES.items():
        m = np.ones(len(cal))
        if cat == "admissions":
            m *= 1 + 3.0 * cal["admissions_window"] + 1.5 * cal["placement_offers"]
            m *= 1 + 4.0 * january * (cal["term_week_1_2"] + cal["pre_term_week"]).clip(0, 1)
        elif cat == "fees_exemptions":
            m *= 1 + 0.8 * cal["month_start"]
            m *= 1 + 1.8 * january * (cal["term_week_1_2"] + cal["term_week_3_4"] + cal["pre_term_week"]).clip(0, 1)
        elif cat == "academic":
            m *= 1 + 0.8 * cal["exam_period"] + 2.0 * cal["report_window"]
        elif cat == "learner_welfare":
            m *= 1 + 0.3 * cal["term_week_1_2"]
        elif cat == "transport":
            m *= 1 + 2.0 * cal["term_week_1_2"]
        elif cat == "it_portal":
            m *= 1 + 0.6 * cal["admissions_window"] + 0.5 * january
        rates[cat] = base * m * season * dow * growth

    for (day, cat), factor in SHOCKS.items():
        if pd.Timestamp(day) in rates.index:
            rates.loc[pd.Timestamp(day), cat] *= factor
    return rates


def _pick(rng, mix: dict) -> str:
    keys = list(mix)
    return keys[rng.choice(len(keys), p=np.array(list(mix.values())) / sum(mix.values()))]


def generate_tickets(start, end, seed: int = 42, now: datetime | None = None) -> list[dict]:
    """Ticket dicts (ready to insert) for every day between start and end."""
    rng = np.random.default_rng(seed)
    now = now or datetime.now(TZ)
    rates = expected_rates(start, end)
    tickets, n = [], 0

    for day, row in rates.iterrows():
        total_today = 0
        for cat, lam in row.items():
            count = rng.poisson(lam)
            total_today += count
            for _ in range(count):
                n += 1
                tickets.append(_make_ticket(rng, cat, day, n, now))
        # Busy days get slower first responses (shows the cost of being under-staffed).
        slowdown = 1 + max(0, total_today - 20) / 20
        for t in tickets[len(tickets) - total_today:]:
            _add_response_times(rng, t, slowdown, now)
    # References count up per day in time order, like crud.generate_reference: SC-YYYYMMDD-0001.
    # Channels use their own random stream, so adding this field did not change the history.
    channel_rng = np.random.default_rng(seed + 1)
    for t in tickets:
        t["channel"] = CHANNELS[channel_rng.integers(len(CHANNELS))]
    tickets.sort(key=lambda t: t["created_at"])
    per_day: dict[str, int] = {}
    for t in tickets:
        day = f"{t['created_at']:%Y%m%d}"
        per_day[day] = per_day.get(day, 0) + 1
        t["reference"] = f"SC-{day}-{per_day[day]:04d}"
        t.pop("first_response_at")              # only used to set status; not a ticket column
        # Store every timestamp in UTC (the database convention for all tickets).
        for key in ("created_at", "updated_at", "resolved_at"):
            if t[key] is not None:
                t[key] = t[key].astimezone(timezone.utc)
    return tickets


def _make_ticket(rng, cat, day, n, now) -> dict:
    templates = TEMPLATES[cat]
    lang = _pick(rng, LANGUAGE_MIX)
    if lang not in templates:
        lang = "en"
    grade = GRADES[rng.integers(len(GRADES))]
    message = templates[lang][rng.integers(len(templates[lang]))].format(g=grade)
    hour = int(rng.choice([7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
                          p=[.04, .1, .1, .09, .08, .07, .07, .08, .08, .07, .07, .06, .05, .04]))
    created = datetime.combine(day.date(), time(hour, int(rng.integers(60))), TZ)
    urgency = _pick(rng, URGENCY_MIX[cat])
    return {
        "reference": None,                      # assigned in date order at the end
        "message": message,
        "parent_name": None,                    # synthetic tickets never have personal data
        "parent_contact": None,
        "learner_grade": grade,
        "channel": None,                        # filled from a separate random stream below
        "category": cat,
        "urgency": urgency,
        "language": lang,
        "routed_role": CATEGORIES[cat].routed_role,
        "confidence": 1.0,
        "method": "rules",
        "needs_human": cat == "learner_welfare",
        "safety_flag": urgency == "critical",
        "reason": "synthetic history",
        "status": "new",
        "created_at": created,
        "updated_at": created,
        "first_response_at": None,
        "resolved_at": None,
    }


def _add_response_times(rng, t, slowdown, now):
    created = t["created_at"]
    hours = rng.gamma(2.0, 6.0) * slowdown
    if t["category"] == "learner_welfare":
        hours = rng.uniform(0.2, 3.0)  # welfare is always handled quickly
    first = created + timedelta(hours=float(hours))
    resolved = first + timedelta(hours=float(rng.gamma(2.0, 12.0) * slowdown))
    if first <= now:
        t["first_response_at"] = first
        t["status"] = "in_progress"
    if resolved <= now:
        t["resolved_at"] = resolved
        t["status"] = "resolved"
    t["updated_at"] = t["resolved_at"] or t["first_response_at"] or created
