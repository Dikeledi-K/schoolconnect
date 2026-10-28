# Changelog

All notable changes, one section per bootcamp week.

## [week-7] 2026-10-28: Workflow Automation & System Integration

### Added
- Staff accounts and login (`app/auth/`): PBKDF2-SHA256 passwords (stdlib, per-user salt,
  `PASSWORD_HASH_ITERATIONS`, default 600 000), 15-minute lockout after 5 failures, 8-hour bearer
  tokens stored as SHA-256 hashes. `POST /auth/login`, `/auth/logout`, `GET /auth/me`, `GET /staff`.
  `scripts/create_staff.py`. Tables `staff`, `staff_sessions`. Role `principal` in `app/taxonomy.py`
  (`ACCOUNT_ROLES`, `SENIOR_ROLES`).
- Least-privilege access (`app/auth/access.py`): own role or assigned tickets; learner-welfare and
  safety tickets for the deputy principal and principal only; forecast and risk endpoints for those
  two roles only; hidden tickets answer 404.
- `ticket_events` table and `app/workflow/events.py`; `GET /tickets/{id}/events`;
  `POST /tickets/{id}/assign` (reassignment, logged and notified).
- Idempotent startup migration `app/db.py: migrate()` (ALTER TABLE ADD COLUMN for missing columns;
  SQLite and Postgres). New ticket columns: `assigned_to`, `first_response_at`, `escalation_level`,
  `escalated_at`.
- One intake path for every channel (`app/workflow/intake.py`) and auto-assignment by least open
  hours (`app/workflow/assignment.py`, handling minutes from `config/workload.yaml`).
- `config/workflow.yaml` and `app/workflow/sla.py`: first-response targets matching
  `school_info.yaml`, school days and office hours from the Week 5 calendar; SLA on every ticket;
  `GET /workflow/my-work`.
- `app/workflow/escalation.py` and `POST /jobs/escalate` (X-Jobs-Token): one level up the chain,
  idempotent, 30-minute critical alert to the deputy principal and principal; events + audit rows.
- Outbox notifications (`app/notify/`, `outbox` table): `NOTIFY_MODE=dry_run|smtp`, SMTP settings,
  phone contacts `not_supported`; approved replies are sent; resolved and fee-decision letters to
  parents; staff alerts with no message text or personal details. `GET /tickets/{id}/outbox`.
- Fee exemption workflow (`app/workflow/fee_exemption.py`, `app/api/fees.py`, `fee_exemptions`
  table): submitted → finance review → principal decision → approved/declined → parent notified.
- Signed inbound webhook `POST /integrations/inbound-message` (HMAC-SHA256 over `timestamp.body`,
  `INBOUND_SECRET`, 5-minute replay window); `docs/INTEGRATIONS.md`.
- Streamlit: `frontend/auth.py` (login form, `require_login(roles=...)`, logout), new pages *My work*
  and *Fee exemptions*; inbox shows assignee, SLA, timeline, reassignment and delivery status;
  parent "Check my message" with plain-language status and reply status.
- `scripts/demo_week7.py`; `docs/weekly/WEEK_7.md`.
- Tests: `test_auth.py`, `test_migration_and_events.py`, `test_notifications.py`, `test_assignment.py`,
  `test_sla_escalation.py`, `test_fee_exemption.py`, `test_inbound.py`, `test_frontend_api_client.py`
  (326 tests in total).

### Changed
- Staff endpoints need `Authorization: Bearer <token>` (the optional `API_KEY` still applies on top).
  Parent endpoints (`POST /tickets`, `GET /tickets/by-reference/...`) are unchanged.
- Typed-in `actor` / `approved_by` fields are optional and ignored: the logged-in staff member is recorded.
- `GET /tickets/by-reference/...` also returns `reply_status`; `TicketOut` has `assigned_to`,
  `first_response_at`, `escalation_level` and `sla`; `ResponseOut` has `delivery_status`.
- Retention / anonymisation also cleans outbox rows.
- Frontend pages renumbered (1 Send, 2 My work, 3 Staff inbox, 4 Fee exemptions, 5 Forecast, 6 Risk);
  "warm & friendly" theme (`.streamlit/config.toml`, `frontend/ui.py`).
- CI also installs `frontend/requirements.txt` (for the api_client tests). API version 0.7.0.

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
