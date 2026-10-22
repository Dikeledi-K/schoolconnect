# SchoolConnect

**An AI help desk for South African public schools.**

Parents send messages in English, isiZulu, Sesotho, Afrikaans or isiXhosa about
admissions, fees, academics, learner welfare, transport and the school portal.
SchoolConnect classifies each message, replies, routes it to the right staff
member, tracks everything, forecasts busy periods, protects learner data under
POPIA, and produces reports for the principal and SGB.

> Status: **Week 1 of 8 complete**: classification engine, ticket API and a basic Streamlit app.
> See [docs/ROADMAP.md](docs/ROADMAP.md).

## The problem
School offices are overwhelmed (especially in January and during admissions),
teachers are pulled into admin, messages get lost in WhatsApp groups, and parents
wait days for answers.

## Features by week
| Week | Module | Status |
|------|--------|--------|
| 1 | System design & ticket classification engine | ✅ done |
| 2 | Automated response generation | planned |
| 3 | Data tracking & analytics dashboard | planned |
| 4 | Business reporting automation | planned |
| 5 | Predictive insights | planned |
| 6 | AI risk & compliance layer | planned |
| 7 | Workflow automation & integration | planned |
| 8 | Deployment & showcase | planned |

### What works now (Week 1)
- Classifies every message into one of 7 categories, 4 urgency levels and 5 languages, and routes it to a staff role.
- Works **fully offline** with a rule-based classifier; optionally uses Claude or Gemini, falling back to rules on any failure.
- **Child-safety guardrails** on every result: abuse, missing children, weapons or self-harm are always `critical`, routed to the deputy principal, and flagged for a human.
- Ticket API with reference numbers (`SC-YYYYMMDD-XXXX`), filters, status changes and stats.
- Streamlit pages: *Send a message* (parents), *Staff inbox*, *Overview*.

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

uvicorn app.main:app --reload          # API on http://localhost:8000 (docs at /docs)
streamlit run frontend/Home.py         # in a second terminal: UI on http://localhost:8501
```

To use Claude, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` in `.env`.
Without a key the app silently uses the rules classifier.

## Project structure
```
app/            FastAPI backend (taxonomy, classifier, models, API)
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
- [Changelog](CHANGELOG.md)
- Weekly reports: [Week 1](docs/weekly/WEEK_1.md)

## Live links
_Coming in Week 8._

## Screenshots
_Coming soon._

## What I learned
_Written at the end of the bootcamp._
