# Weeks 3–4 – Analytics Dashboard & Weekly Business Reports

Weeks 3 and 4 were skipped when the bootcamp schedule jumped from Week 1 to Week 5. They were built
after Week 7, so they use the Week 7 data (first responses, escalations, staff logins) and the
Week 5 forecast.

**Week 3 sprint goal:** introduce data monitoring. **Feature:** Analytics & Tracking Dashboard.
**Outcome:** the platform produces measurable business insights.

**Week 4 sprint goal:** add executive-level reporting. **Feature:** Automated Weekly Business Report
Generator. **Outcome:** end-to-end reporting automation integrated.

## What was built

1. **Metrics engine** (`app/analytics/metrics.py`) for any period and department, compared with the
   period before: volume by topic, urgency, language, channel, grade band and day; median and
   90th-percentile **first-response and resolution times in office hours**; the share **answered
   within the promised time** (the same promises as the Week 7 SLA and `school_info.yaml`); backlog
   and overdue at the end of the period; escalations; parents who wrote more than once. Plus
   week-by-week trends.
2. **Weekly summary insights** (`app/analytics/insights.py`): plain-language wins, concerns and
   notes built only from the figures.
3. **Analytics page**: department and period filters, KPI tiles with change, three trend charts,
   topic table, breakdowns, and a "how these figures are worked out" explainer.
4. **Weekly business report (PDF)** for the whole school (principal & SGB) and each department
   (admin, finance, teaching, learner welfare, IT): executive summary, key figures vs last week,
   8-week charts, topics, wins and concerns, and **next week's outlook** from the Week 5 forecast.
5. **Optional AI executive summary**: rewritten in plainer English only if every number matches the
   figures; otherwise the template is used. Logged in the AI audit log.
6. **Stored reports** (`weekly_reports`) and a **Weekly reports** page to make, list and download them.
7. **Automation**: `POST /jobs/weekly-reports` (scheduler, idempotent) and
   `scripts/make_weekly_reports.py`; readers get a "your report is ready" email (no figures in it).
8. **Access by role**: principal sees every department; deputy sees the whole school and learner
   welfare; everyone else sees their own department.
9. **Fixes found on the way**: the demo history now keeps first-response times and starts on a fixed
   date (so documented results reproduce on any day); the forecasting model runs single-threaded
   (later forecasts in the API were up to 4× slower).

## Curriculum mapping

| Curriculum item | Where |
|---|---|
| Week 3: store ticket data in structured format | `tickets`, `ticket_events`, `responses` tables (Weeks 1, 6, 7) |
| Week 3: analyse trends (volume, categories, response time) | `compute_metrics`, `weekly_trends` |
| Week 3: build visual dashboard | Analytics page |
| Week 3: generate weekly summary insights | `build_insights`, shown on the page and in the report |
| Week 4: convert dashboard insights into automated summaries | `executive_summary` (template or number-checked AI) |
| Week 4: generate downloadable PDF or structured report | `app/reports/pdf.py`, `GET /reports/{id}/pdf`; JSON in `weekly_reports.data` |
| Week 4: customise reporting per department | `DEPARTMENT_NAMES`, `categories_for_department`, access by role |

## Grading rubric mapping

**Week 3 – Technical (60%): effective prompts, useful outputs. Professional (40%): relevance, clarity, tone.**

| Evidence |
|---|
| Every metric tested on hand-built tickets with answers worked out on paper (e.g. Friday 15:00 → Monday 08:30 = 1.5 office hours) |
| The AI summary prompt is constrained (facts only, copy numbers exactly) and its output is checked; a test proves an invented "250" is rejected |
| Insights are short, specific and actionable, in a warm, plain tone for a principal |

**Week 4 – Technical (50%): functional tool. Professional (50%): responsible AI use, presentation quality.**

| Evidence |
|---|
| One click (or one scheduled call) makes six department PDFs; a second run does nothing (idempotent) |
| Counts only; no personal data in reports or emails; each person sees only their own department |
| Rounding never hides a miss (89.5% vs a 90% target is not shown as "90%") |
| A clean one/two-page PDF with charts that use one measure each (no confusing dual axes) |

## 5-minute demo script

Setup: `python scripts/generate_history.py --reset`, `python scripts/demo_week7.py --password "..."`,
then `python scripts/make_weekly_reports.py --weeks 4`. Log in as `principal@ubuntu-demo.school.example`.

1. **(30s) The question.** "The principal and the SGB ask every week: how busy were we, did parents
   get answers, and did we keep our promises? Until now that meant scrolling WhatsApp."
2. **(75s) Analytics.** Open *Analytics*, last week. Read the four tiles (messages, median first
   response, answered on time, still open), then the "What happened" insights. Point at the trend
   charts: busy weeks and slower replies line up.
3. **(60s) The January story.** Choose dates 12–18 January 2026: **160 messages, up 88%, mainly
   admissions; replies slowed from 2.8 to 5.6 office hours**, but 93% were still on time.
4. **(60s) The report.** *Weekly reports* → make the whole-school report for the week of 12 January
   and download it. Show the executive summary, key figures vs last week, the two charts, wins and
   concerns, and the outlook: made on 19 January, it expected **179** messages the next week;
   **188** arrived.
5. **(45s) Per department, safely.** Log in as `finance@…`: the finance clerk sees only the Finance
   office report. Mention: counts only, no names; the "report ready" email has no figures.
6. **(30s) Automation.** "Every Monday the scheduler makes all six reports and tells each reader.
   Run it twice and nothing is duplicated." Close: "From raw messages to an SGB-ready report with no
   copying and pasting."

## Known limitations

- Response times use the first response recorded in the system; a phone call that is never logged
  does not count.
- The whole-school figures do not separate escalated tickets by the role that finally handled them
  (department = the topic's original routing).
- The demo history has no built-in reporting quirks, so the reports look tidier than real data will.
- With no AI configured, the executive summary is assembled from the insight templates (clear, but
  less fluent).
- The job takes about 15–30 seconds with the forecast outlook (about 150 s on Render's free CPU).
  Week 8 therefore runs it on GitHub Actions, straight against Supabase (`docs/DEPLOYMENT.md`).

## Retrospective questions

1. Which single figure on the report would a principal act on first, and is it the most prominent
   thing on the page?
2. "Office hours" makes Friday-evening messages look fast. Is that fair to parents, or should the
   report also show clock time?
3. What would make the SGB trust these numbers enough to use them in a funding or staffing request?
