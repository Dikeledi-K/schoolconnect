# Changelog

All notable changes, one section per bootcamp week.

## [week-5] 2026-10-26: Predictive Insights Module

Weeks 2–4 were skipped when the bootcamp schedule moved to Week 5 (see docs/ROADMAP.md).

### Added
- `app/forecasting/`: calendar features, daily counts, four forecasting methods, rolling
  backtest with per-category model choice, 80% ranges, workload per staff role (busy-week and
  staff scenarios), spike detection and plain-language recommendations.
- `config/school_calendar.yaml` (approximate SA calendar 2024–2027) and `config/workload.yaml`.
- `app/synthetic.py` + `scripts/generate_history.py`: ~24 months of synthetic ticket history.
- `scripts/evaluate_forecast.py` → `docs/forecast_evaluation.md`.
- `forecast_runs` table; `crud.ticket_timestamps()`.
- Endpoints: `GET /analytics/history`, `/forecast`, `/forecast/workload`, `/forecast/surges`,
  `/forecast/insights`, `/forecast/evaluation` (API key), `POST /jobs/refresh-forecast` (X-Jobs-Token).
- Setting `JOBS_TOKEN`.
- Streamlit page *Forecast and workload* (live + backtest views); link on Home.
- Tests: `tests/test_forecasting.py`, `tests/test_forecast_api.py`.
- Docs: `docs/FORECASTING.md`, `docs/weekly/WEEK_5.md`; README, ROADMAP, ARCHITECTURE, DATA updated.

### Changed
- `requirements.txt`: pandas, numpy, scikit-learn, pyyaml. `frontend/requirements.txt`: plotly; streamlit ≥ 1.46.
- API version 0.5.0. Frontend API client timeout 60 s and a clear message for "not enough history" (409).

## [week-1] 2026-10-22: System Design & Ticket Classification Engine

### Added
- Project setup: `CLAUDE.md`, `docs/ROADMAP.md`, `.gitignore`, `requirements.txt`,
  `.env.example`, `pytest.ini`, GitHub Actions CI (pytest on Python 3.11).
- `app/taxonomy.py`: 7 categories with routed staff roles and keywords in
  English, isiZulu, Sesotho, Afrikaans and isiXhosa; urgency levels; languages;
  statuses; safety keywords.
- Classifier (`app/classifier/`): offline rules, optional Claude/Gemini with
  strict JSON and validation, rules fallback, and child-safety guardrails that
  only raise urgency.
- Database (`Ticket` model, SQLite locally) with `SC-YYYYMMDD-XXXX` references.
- API: `/health`, `/taxonomy`, `/classify`, `/tickets` (create, list with
  filters, get, by reference, status update), `/stats`; CORS; optional `X-API-Key`.
- 150 synthetic sample messages (`data/sample_messages.csv`, `docs/DATA.md`) and
  `scripts/seed_db.py` (dates spread over 60 days).
- `scripts/evaluate_classifier.py` → `docs/classifier_evaluation.md`
  (96.0% accuracy, 0 missed critical cases).
- Streamlit frontend: Overview, Send a message, Staff inbox.
- 96 tests: taxonomy, rules, guardrails, mocked LLM, prompt injection, API, data and targets.
- `docs/ARCHITECTURE.md` with Mermaid diagrams.
