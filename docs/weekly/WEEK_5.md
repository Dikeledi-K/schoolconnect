# Week 5 – Sprint 3: Predictive Insights Module

**Sprint goal:** introduce forecasting capability.
**Feature built:** Trend Prediction Component (ticket forecast, workload projection, spike alerts, recommendations).
**Outcome:** the platform now supports forward-looking decision-making.

## What was built

Built on top of the Week 1 classification engine (Weeks 2–4 were skipped when the bootcamp
schedule moved to Week 5).

1. **Historical data:** ~24 months of synthetic, calendar-driven tickets (about 9,800).
2. **School calendar features:** term starts, start of the school year, admissions windows,
   placement offers, exams, report days, holidays and public holidays.
3. **Four forecasting methods**, from "same as last week" to a scikit-learn model, chosen per
   topic by a leakage-free rolling backtest.
4. **Projected workload** per staff role, with a busy-week scenario and a staff "what if" control.
5. **Spike detection** with likely causes and extra staff hours.
6. **Plain-language recommendations** for the principal.
7. **Forecast and workload page** with a backtest demo view.
8. **API** endpoints under `/forecast/*`, stored forecast runs and a protected refresh job.
9. Tests for every part (123 tests in total, including Week 1), and documentation.

## Curriculum mapping

| Curriculum item | Where |
|---|---|
| Use historical data | `scripts/generate_history.py`, `app/forecasting/data.py` |
| Build simple predictive logic (e.g. ticket surge forecast) | `app/forecasting/models.py`, `evaluate.py`, `surges.py` |
| Display projected workload | `app/forecasting/workload.py`, Forecast & Workload page (heatmap + weekly table) |
| Alignment: apply analytical models for forecasting | backtest, model comparison and selection, prediction intervals |

## Grading rubric mapping

**Technical skills (60%)**

| Criterion | Evidence |
|---|---|
| Accurate analysis | 22% error vs 30% baseline (backtest 20 Oct – 14 Dec 2025); January rush forecast within 16%; admin clerk 86% forecast vs 88% actual ([forecast_evaluation.md](../forecast_evaluation.md)); no-leakage test |
| Working dashboard | Streamlit page: KPIs, history + forecast chart with calendar and 80% range, workload heatmap, scenario control, spikes, accuracy table |

**Professional skills (40%)**

| Criterion | Evidence |
|---|---|
| Insight explanation | Recommendations panel, "How it works" explainer, [FORECASTING.md](../FORECASTING.md) |
| Business relevance | Answers "who is overloaded, when, what to do"; actions tied to each topic; staff scenario |

## 5-minute demo script

1. **(30s) The problem.** "Every January the school office is swamped. Nobody plans for it,
   even though it happens every year."
2. **(60s) Live view.** Open *Forecast and workload* (from Home: "Principal: forecast & staff workload"). Read the KPI tiles: expected messages, busiest
   day, roles needing attention. Read the top recommendation aloud.
3. **(90s) Backtest demo — the key moment.** Switch to *Backtest demo*, date 15 Dec 2025, 45 days.
   "It is mid-December. The system only knows the past." Show the forecast rising in January,
   then the blue line of what *really* happened. Show the recommendation: admin clerk at 86%
   (105% in a busy week) in the week of 19 January. In the weekly table: **actual 88%**.
4. **(45s) Scenario.** Open "What if staff capacity changes?", set Admin Clerk to 2 — utilisation
   halves. "A temporary assistant for two weeks solves it."
5. **(45s) Trust.** Scroll to "How accurate is this?" (backtest view, 15 Dec 2025): 22% error vs 30% for the simple rule;
   machine learning is only used where it beats simple methods.
6. **(30s) Honesty and next steps.** Synthetic data, approximate calendar, one previous January.
   Week 6 adds POPIA protection, bias checks and audit logs.

## Known limitations

- Synthetic data and an approximate calendar.
- January peak slightly under-forecast (only one previous January in history).
- Learner welfare volumes are too low for precise percentage accuracy.
- Handling minutes in `config/workload.yaml` are estimates.
- First forecast request takes a few seconds before it is cached.
- Generating history replaces the 150 Week 1 demo tickets (`seed_db.py`) for forecasting demos.
- Results vary with the random history: another draw gave 25% January error instead of 16%.

## Retrospective questions

1. Which assumption in `config/workload.yaml` would change the recommendations most, and how
   could a real school measure it cheaply?
2. When the ML model and a simple method are nearly equally accurate, which should the school
   trust, and why?
3. What would make a principal ignore these recommendations, and how could the dashboard earn
   their trust over a full school year?
