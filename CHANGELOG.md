# Changelog

All notable changes, one section per bootcamp week.

## [week-6] 2026-10-26: AI Risk & Compliance Layer

### Added
- Reply drafts (from the skipped Week 2): `config/school_info.yaml` (fictional demo school),
  `app/responses/` templates in three tones, optional AI rewrite with a grounding check,
  acknowledgement-only replies for welfare/safety, staff edit and approval. `responses` table.
- `app/privacy/pii.py`: masking of SA ID numbers (Luhn), phone numbers, emails, long numbers and known
  names; applied before every LLM call and to all log records.
- `ai_audit_log` table and `app/audit.py`; audit rows for classification, reply drafts, edits,
  approvals, corrections, anonymisation and retention.
- Staff corrections (`PATCH /tickets/{id}/classification`) with guardrails re-applied.
- `app/risk/`: fairness checks, prompt-injection suite (`data/prompt_injection_cases.json`), risk
  summary and PDF report (reportlab); `config/risk_register.yaml`.
- `app/privacy/retention.py`, `POST /jobs/retention` (dry run by default), `POST /privacy/tickets/{id}/anonymise`.
- Endpoints: replies (`/tickets/{id}/responses`, `/responses/{id}`, `/responses/{id}/approve`),
  `/tickets/{id}/audit`, `/risk/summary`, `/risk/fairness`, `/risk/report.pdf`.
- Streamlit: Staff inbox transparency notes, "Correct the AI", reply panel, audit trail, privacy action;
  new *Risk and compliance* page.
- `scripts/demo_week6.py`; `docs/POPIA.md`, `docs/weekly/WEEK_6.md`.
- Setting `RETENTION_DAYS` (default 365). Dependency `reportlab`.
- Tests: `test_pii.py`, `test_responses.py`, `test_prompt_injection.py`, `test_compliance_api.py`,
  `test_fairness.py` (185 tests in total).

### Changed
- `classify_message()` takes `names=` and masks the text before the LLM call.
- A corrected ticket's method becomes `staff` (confidence 1.0); the AI's original is in the audit log.

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
