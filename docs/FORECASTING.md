# How the forecasting works

## The business question

> Which staff member will be overloaded, when, and what should the principal do about it?

A school office cannot hire help on the day the rush arrives. It needs a few weeks' warning.
SchoolConnect turns past parent messages and the school calendar into a 14–60 day forecast,
converts it into staff hours, and says in plain language where the pressure will be.

## Data

Daily counts of parent messages per category (admissions, fees & exemptions, academic, learner
welfare, transport, IT & portal, other), counted in South African time and zero-filled for days
with no messages. Only `created_at` and `category` are used; no personal data.

The demo uses ~24 months of synthetic history (see [DATA.md](DATA.md)).

## Calendar features

From `config/school_calendar.yaml` each day gets yes/no flags:

| Feature | Why it matters |
|---|---|
| weekend, public holiday, school day, holiday break | offices are quiet when schools are closed |
| week before term, first two weeks, weeks 3–4 of term | parents call when term starts |
| start of the school year | the biggest rush of the year (January) |
| admissions window, placement offers | admissions and portal queries |
| exam period, reports issued | academic queries |
| month start | fee payments and statements |

## Four methods, from simple to machine learning

| Method | How it works | Strength | Weakness |
|---|---|---|---|
| Same as last week | next Monday = last Monday | trivial to explain | fails at every term start or holiday |
| Same day last year | 52 weeks ago × this year's growth | captures the yearly cycle | dates shift a little each year |
| Recent average | average of recent school days, adjusted for weekday, weekends and holidays | stable for low, steady topics | does not know about term starts |
| Machine learning | gradient boosting (scikit-learn) on calendar features + last year's value | learns "admissions spike in the first week of the year" | needs history; harder to explain |

**Why simple models?** The school needs something it can trust and explain. Heavy libraries
(Prophet, deep learning) would also not fit the deployment size limit. The ML model is small
(about 150 shallow trees) and trains in under a second per category.

## Choosing a method fairly (backtesting)

We pretend it is an earlier date, forecast the next 14 days using **only data from before that
date**, and compare with what really happened. This is repeated for four starting points
covering the last 8 weeks (rolling-origin backtest). A test checks that no future data leaks in.

Two error measures:

- **MAE**: on average, how many messages per day we were off by.
- **WAPE**: total error ÷ total messages. 20% means "20% off overall". Lower is better.

For each category we take the most accurate simple method, and use machine learning **only if
it is at least 2% better**. A complicated model must earn its place.

## Uncertainty (the 80% range)

From the backtest we learn how far actual numbers usually landed from the forecast, as a
multiplier. For example, if actual totals were usually between 0.7× and 1.5× the forecast, the
shaded band on the chart is 0.7×–1.5× the forecast line. The daily total has its own band learned
from total errors, because adding up category bands would overstate the uncertainty.

## From messages to staff hours

`config/workload.yaml` sets average handling minutes per topic (e.g. admissions 15, welfare 45)
and the hours per day each role has for parent messages.

- hours needed = forecast messages × handling minutes, grouped by the role each topic routes to
- weekend and public-holiday messages are added to the next office day
- capacity = staff × hours per day (halved during school holidays)
- utilisation = hours needed ÷ capacity: **OK** below 80%, **busy** 80–100%, **overloaded** above 100%
- **busy-week scenario**: hours needed × (1 + the forecast's own average backtest error, about 22%).
  A role that copes on average but would be overloaded in a busy week is flagged as a *risk*.

The scenario box in the UI lets the principal change staff numbers and immediately see the effect.

## Spikes

A day is a spike if its forecast is at least **1.5× a normal recent day** (median of the same
weekday over the last 4 weeks) and at least 5 messages higher. The likely cause comes from the
calendar flags for that day, and the extra staff hours from the topics that grew most.

## Recommendations

Built from the numbers with fixed templates (no LLM), so they cannot invent facts, e.g.

> Admin Clerk will be busy (86% capacity) in the week of 19 Jan 2026, mainly admissions queries.
> Plan ahead: publish an admissions FAQ and document checklist … In a busy week it could reach 105%.

Only aggregate counts are involved; no personal data. (An optional LLM rewrite of the wording
could be added later, as long as it is rejected whenever it adds a number not in the original.)

## Results (synthetic demo data)

See [forecast_evaluation.md](forecast_evaluation.md) (regenerate with
`python scripts/evaluate_forecast.py`). Headlines:

- Overall error 22% vs 39% for "same as last week" (43% better).
- Forecasting January 2026 from 15 December 2025: 16% error over 12–30 January; 84% of days
  inside the 80% range; admin clerk forecast at 86% of capacity in the week of 19 January,
  actual 88%.

## Limitations

- **Synthetic data.** Real patterns will differ; the method stays the same.
- **Approximate calendar.** Verify against the official DBE and provincial admissions calendars.
- **Only one previous January** in the demo history, so the January peak is under-forecast a
  little. Accuracy improves each year as history grows.
- **Results depend on the random draw.** With a different random sequence of synthetic history,
  the January error was 25% instead of 16%. Quote ranges, not a single lucky number, and re-check
  on real data.
- **Low-volume topics** (learner welfare, about one message a day) have high percentage errors
  even when off by one message. Welfare is always handled by a person regardless.
- **Unpredictable events** (portal crashes, strikes) cannot be forecast from a calendar.
- **Handling minutes are estimates.** A real school should time a sample of tickets.

## How a real school would use it

1. Every Monday (scheduled job in Week 8) the forecast refreshes for the next 60 days.
2. The principal reads the recommendations and checks the workload heatmap.
3. Before a predicted rush: publish FAQs, send statements early, book a temporary assistant,
   block the deputy principal's diary.
4. After the rush: compare forecast with reality in the backtest view, and adjust
   `workload.yaml` if handling times were wrong.
