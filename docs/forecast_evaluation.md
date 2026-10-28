# Forecast evaluation

_Generated 2026-10-28 by `scripts/evaluate_forecast.py` on the synthetic demo data. Re-run after regenerating data._

Methods:

- **Same as last week** (`seasonal_naive`): Same weekday last week. 'Next Monday will look like last Monday.'
- **Same day last year** (`last_year`): Same day last year, scaled by how much busier this year is.
- **Recent average** (`moving_average`): Average of recent school days, adjusted for weekday, weekends and holidays.
- **Machine learning** (`ml_calendar`): Machine learning (gradient boosting) using school-calendar features (term start, admissions window, exams, reports, weekday) and last year's value.

Rule: each category uses its most accurate baseline, and switches to machine learning only if ML is at least 2% better.

## Current forecast

Forecast start (as of): **2026-10-28**. Backtest window: 2026-09-02 to 2026-10-27 (56 days, 4 rolling 14-day forecasts).

| Measure | Value |
|---|---|
| Overall error of SchoolConnect forecast (WAPE) | **21.6%** |
| Simple 'same as last week' rule (WAPE) | 33.0% |
| Improvement over the simple rule | 34% |
| Average error per day (MAE, all messages) | ±3.4 messages |
| 80% range for the daily total | 0.65× to 1.62× the forecast |

WAPE per category and method (lower is better; **bold** = method chosen):

| Category | Same as last week | Same day last year | Recent average | Machine learning |
|---|---|---|---|---|
| academic | 84% | 57% | 56% | **39%** |
| admissions | 77% | 72% | 104% | **54%** |
| fees_exemptions | 58% | 68% | 61% | **46%** |
| it_portal | 64% | 79% | **52%** | 61% |
| learner_welfare | 95% | 144% | 82% | **80%** |
| other | 60% | 78% | 44% | **42%** |
| transport | 72% | 70% | 67% | **46%** |

## Backtest demo: forecasting the January rush

Forecast start (as of): **2025-12-15**. Backtest window: 2025-10-20 to 2025-12-14 (56 days, 4 rolling 14-day forecasts).

| Measure | Value |
|---|---|
| Overall error of SchoolConnect forecast (WAPE) | **22.2%** |
| Simple 'same as last week' rule (WAPE) | 30.2% |
| Improvement over the simple rule | 27% |
| Average error per day (MAE, all messages) | ±3.4 messages |
| 80% range for the daily total | 0.70× to 1.57× the forecast |

WAPE per category and method (lower is better; **bold** = method chosen):

| Category | Same as last week | Same day last year | Recent average | Machine learning |
|---|---|---|---|---|
| academic | 49% | 52% | 46% | **40%** |
| admissions | 67% | **57%** | 63% | 56% |
| fees_exemptions | 83% | 74% | 55% | **54%** |
| it_portal | 85% | 82% | 68% | **62%** |
| learner_welfare | 141% | 129% | **102%** | 101% |
| other | 70% | 70% | **54%** | 54% |
| transport | 95% | 63% | 77% | **61%** |

### January 2026 opening (forecast made on 15 Dec 2025)

- Messages 12–30 Jan: forecast 421, actual 486 (WAPE 16%).
- Days where the actual total fell inside the 80% range: 84%.
- Admin clerk, week of 19 Jan: forecast 86% of capacity (busy-week scenario 105%); actual 88%.
- The model under-forecasts the peak slightly because it has seen only one previous January. Accuracy should improve each year as history grows.

## Notes

- Learner welfare has very low daily counts (about 1 a day), so percentage errors look large even when the forecast is off by only one message. It is planned with a simple average and always handled by a person.
- All data is synthetic and the calendar is approximate (see docs/DATA.md).
