# SchoolConnect

**An AI help desk for South African public schools.**

Parents send messages in English, isiZulu, Sesotho, Afrikaans or isiXhosa about
admissions, fees, academics, learner welfare, transport and the school portal.
SchoolConnect classifies each message, replies, routes it to the right staff
member, tracks everything, forecasts busy periods, protects learner data under
POPIA, and produces reports for the principal and SGB.

> Status: **Weeks 1, 5, 6 and 7 complete** (Weeks 2–4 were skipped by the bootcamp schedule):
> classification, forecasting, AI risk & compliance, and workflow automation. Week 8 deploys it.
> See [docs/ROADMAP.md](docs/ROADMAP.md).

## The problem
School offices are overwhelmed (especially in January and during admissions),
teachers are pulled into admin, messages get lost in WhatsApp groups, and parents
wait days for answers.

## Features by week
| Week | Module | Status |
|------|--------|--------|
| 1 | System design & ticket classification engine | ✅ done |
| 2 | Automated response generation | skipped (schedule change); built in Week 6 |
| 3 | Data tracking & analytics dashboard | skipped; history charts in Week 5 |
| 4 | Business reporting automation | skipped (optional backlog) |
| 5 | Predictive insights | ✅ done |
| 6 | AI risk & compliance layer | ✅ done |
| 7 | Workflow automation & integration | ✅ done |
| 8 | Deployment & showcase | planned |

### What works now (Week 1)
- Classifies every message into one of 7 categories, 4 urgency levels and 5 languages, and routes it to a staff role.
- Works **fully offline** with a rule-based classifier; optionally uses Claude or Gemini, falling back to rules on any failure.
- **Child-safety guardrails** on every result: abuse, missing children, weapons or self-harm are always `critical`, routed to the deputy principal, and flagged for a human.
- Ticket API with reference numbers (`SC-YYYYMMDD-XXXX`), filters, status changes and stats.
- Streamlit pages: *Send a message* (parents), *Staff inbox*, *Overview*.

### What works now (Week 5: Predictive insights)
- Forecasts parent messages per topic for the next 14–60 days, using the school calendar
  (term starts, admissions windows, exams, report days, holidays) and ~24 months of synthetic history.
- Converts the forecast into **staff hours per role** and flags who will be busy or overloaded, and when.
- Spike alerts with the likely cause, plain-language recommendations, a "what if we add staff"
  scenario, and an honest accuracy report.
- **Backtest demo:** pretend it is 15 December 2025, forecast January, then compare with what really happened.

### What works now (Week 6: AI risk & compliance)
- **Privacy:** SA ID numbers, phone numbers, emails and known names are masked before any AI sees a
  message, and in every log line. Staff can anonymise a ticket on request; a retention job anonymises
  old resolved tickets ([docs/POPIA.md](docs/POPIA.md)).
- **Reply drafts** from the school's own facts in three tones; an optional AI rewrite is rejected if
  it invents a number, email or link. Welfare replies are acknowledgement-only. Staff approve every reply.
- **Accountability:** every AI decision and staff correction is in an audit log (no raw personal data).
  Staff corrections cannot lower a child-safety ticket.
- **Fairness** by language and grade, a **prompt-injection suite** (23/23 checks pass), and a
  downloadable **risk evaluation PDF**.

### What works now (Week 7: Workflow automation & integration)
- **End to end with no copying:** received → classified → **auto-assigned** to the person in the
  right role with the least open work → reply drafted → approved → **parent emailed** (through an
  outbox; dry run by default) → **escalated automatically** if nobody responds in time.
- **Staff logins** with roles. Least privilege: learner-welfare tickets are visible only to the
  deputy principal and principal; staff see their own role's and their own tickets.
- **Response-time targets** that match the school's promises (critical 1 hour; high/medium/low
  1/2/5 school days, skipping weekends and public holidays), with "2 h left" / "overdue 3 h" badges.
- **Fee exemption approvals:** finance clerk checks documents and recommends, principal decides,
  parent gets a letter; every step logged.
- **Integrations:** a signed webhook lets an email forwarder or WhatsApp gateway create tickets
  ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)).
- New pages: **My work** and **Fee exemptions**; parents can **check their message** by reference.

## Forecast results (Week 5, synthetic history)
| Measure | Result |
|---|---|
| Forecast error (WAPE), last 8 weeks | **22%** |
| Simple "same as last week" rule | 39% |
| January 2026 rush, forecast from 15 Dec 2025 | 16% error; 84% of days inside the 80% range |
| Admin clerk, week of 19 Jan 2026 | forecast **86%** of capacity, actual **88%** |

Full report: [docs/forecast_evaluation.md](docs/forecast_evaluation.md). How it works:
[docs/FORECASTING.md](docs/FORECASTING.md).

## Evaluation results (rules classifier, 150 synthetic messages)
| Metric | Result | Target |
|---|---|---|
| Category accuracy | **96.0%** (holdout 96.7%) | ≥ 75% |
| Missed critical cases | **0 of 6** | 0 |
| High/critical recall | 83.3% | – |
| Language detection | 97.3% | – |

Full report: [docs/classifier_evaluation.md](docs/classifier_evaluation.md). These numbers are
optimistic because the same person wrote the data and the rules; see [docs/DATA.md](docs/DATA.md).

## Tech stack
Python 3.11+ · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · Streamlit · SQLite / Supabase Postgres ·
Anthropic Claude (optional) · plotly · reportlab · pandas + scikit-learn · pytest · GitHub Actions · Vercel

## How to run (local)
```bash
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r frontend/requirements.txt
copy .env.example .env                 # macOS/Linux: cp .env.example .env

pytest                                 # run the tests (no internet or API key needed)
python scripts/seed_db.py --reset      # load 150 demo tickets
python scripts/evaluate_classifier.py  # writes docs/classifier_evaluation.md

# Week 5 forecasting demo (replaces the 150 demo tickets with ~24 months of history):
python scripts/generate_history.py --reset
python scripts/evaluate_forecast.py    # writes docs/forecast_evaluation.md
python scripts/demo_week6.py           # Week 6: live tickets, corrections and replies for the demo
python scripts/demo_week7.py --password "pick-a-demo-password"   # Week 7: demo staff + full workflow
python scripts/create_staff.py --name "Mrs Pillay" --email pillay@school.example --role finance_clerk

uvicorn app.main:app --reload          # API on http://localhost:8000 (docs at /docs)
streamlit run frontend/Home.py         # in a second terminal: UI on http://localhost:8501
```

To use Claude, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` in `.env`.
Without a key the app silently uses the rules classifier.

Staff pages need a login (the demo script prints the demo logins). Parents never log in.
Notifications stay in the outbox (`NOTIFY_MODE=dry_run`) until you configure SMTP in `.env`.
Set `JOBS_TOKEN` to use `POST /jobs/escalate`, and `INBOUND_SECRET` to enable the webhook.

## Project structure
```
app/            FastAPI backend (taxonomy, classifier, forecasting, privacy, auth, workflow, notify, API)
config/         school facts, calendar, staff workload, workflow rules and risk register (YAML)
frontend/       Streamlit app (talks to the API over HTTP only)
data/           synthetic sample messages
scripts/        seed and evaluation scripts
tests/          pytest suite
docs/           architecture, roadmap, data, evaluation, weekly reports
```

## Documentation
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Sample data](docs/DATA.md)
- [Classifier evaluation](docs/classifier_evaluation.md)
- [How the forecasting works](docs/FORECASTING.md) · [Forecast evaluation](docs/forecast_evaluation.md)
- [POPIA: how personal information is protected](docs/POPIA.md)
- [Integrations: signed webhook for email / WhatsApp](docs/INTEGRATIONS.md)
- [Changelog](CHANGELOG.md)
- Weekly reports: [Week 1](docs/weekly/WEEK_1.md) · [Week 5](docs/weekly/WEEK_5.md) · [Week 6](docs/weekly/WEEK_6.md) · [Week 7](docs/weekly/WEEK_7.md)

## Live links
_Coming in Week 8._

## Screenshots
_Coming soon._

## What I learned
_Written at the end of the bootcamp._
