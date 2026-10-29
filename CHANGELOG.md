# Changelog

All notable changes, one section per bootcamp week.

## [week-8] 2026-10-29: Deployment, Optimisation & Industry Showcase

### Added
- `render.yaml` Render Blueprint: `schoolconnect-api` (FastAPI) and `schoolconnect-web` (Streamlit, from
  the repo root so the theme loads), free plan, Frankfurt, auto-deploy from `main`, secrets `sync: false`.
- `.python-version` (3.11) for Render and CI; `requirements-dev.txt` (pytest, psutil, playwright).
- `app/db.py`: `normalise_url()`, `engine_options()` for Supabase (psycopg 3, pool 3 + 2, `pool_pre_ping`,
  `pool_recycle=300`, `sslmode=require`, prepared statements off on the transaction pooler port 6543).
- `ENVIRONMENT` setting and `check_production_settings()`: production refuses to start without
  `API_KEY` / `JOBS_TOKEN`, with weaker password hashing, or on SQLite.
- "Demo: fictional school, synthetic data" banner on every page and in the API docs.
- `stored_forecasts` table: signed (HMAC with a key from `JOBS_TOKEN`), pickled forecast bundles for
  today and `FORECAST_PINNED_DATES` (default 2025-12-15); endpoints read them before computing.
  `scripts/refresh_forecasts.py`; `/jobs/refresh-forecast` also stores them.
- `.github/workflows/jobs.yml`: escalation (every 15 min), keep-warm (every 14 min), dry-run retention
  as calls to Render; forecasts (daily) and weekly reports (Mondays) run on GitHub against Supabase.
  `scripts/call_endpoint.py` (180 s timeout, one retry, fails loudly).
- `scripts/smoke_test_prod.py` (9 checks with timings), `scripts/measure_performance.py` (peak memory,
  optional Windows 0.1-core CPU cap), `scripts/take_screenshots.py` (Playwright, `docs/screenshots/`).
- Docs: `docs/DEPLOYMENT.md`, `docs/TECHNICAL.md`, `docs/USER_GUIDE.md`, `docs/BUSINESS_CASE.md`,
  `docs/PRESENTATION.md`, `docs/weekly/WEEK_8.md`; portfolio `README.md`.
- Tests: `test_deployment_config.py`, `test_production.py`, `test_stored_forecast.py`, `test_jobs.py`,
  `test_smoke_test.py`, `test_optimisation.py` (402 tests in total).

### Changed
- Deployment target: Render + Supabase + GitHub Actions (no Vercel, no Streamlit Community Cloud).
- `requirements.txt` is runtime only (adds `psycopg[binary]`, drops pytest); CI installs `requirements-dev.txt`.
- Workload maths reads the forecast table once into a dict: 30–60× faster, identical results.
- scikit-learn is imported only when a forecast is computed (API start-up 4.9 s to 2.8 s).
- The classifier fairness check is cached per process; the Risk page builds its PDF only on request;
  the inbox fetches the audit trail once; spinners on slow actions; staff list and risk summary cached
  for 2 minutes per login.
- Sidebar: colours and icons for all 9 pages (the selected "Forecast" label was white on white).
- Parent reference lookup ignores punctuation around the reference (e.g. a copied full stop), and
  the confirmation shows the reference on its own with a copy button.
- `evaluate_forecast.py` writes UTF-8 on every platform.
- Settings and the job caller trim spaces and line breaks around pasted secrets (a `DATABASE_URL`
  with a trailing newline broke the first GitHub job).

### Deployed
- Live on Render (https://schoolconnect-web-cwa0.onrender.com, API https://schoolconnect-api-0yhr.onrender.com)
  with Supabase Postgres (West EU), seeded with the demo; all 5 scheduled jobs green; live smoke test 9/9.

## [weeks-3-4] 2026-10-28: Analytics dashboard and weekly business reports

Weeks 3 and 4 were skipped in the bootcamp schedule; built now on top of Week 7.

### Added
- `app/analytics/metrics.py`: figures for any period and department vs the previous period
  (volumes, office-hour first-response and resolution times, answered within the promised time,
  backlog, escalations, repeat contacts) and weekly trends.
- `app/analytics/insights.py`: plain-language wins/concerns, executive summary (optional AI,
  rejected if it adds numbers; audit-logged), next week's outlook from the Week 5 forecast.
- `app/reports/` (`weekly.py`, `pdf.py`): weekly PDF per department and for the whole school,
  stored in a new `weekly_reports` table; access by role.
- Endpoints: `/analytics/scopes`, `/analytics/summary`, `/analytics/trends`, `/reports/weeks`,
  `/reports`, `POST /reports/weekly`, `/reports/{id}/pdf`, `POST /jobs/weekly-reports`.
- Streamlit pages *Analytics* and *Weekly reports*; Home cards; pages renumbered (Forecast 8, Risk 9;
  URLs unchanged).
- `scripts/make_weekly_reports.py`; `DEPARTMENT_NAMES` and `categories_for_department` in the
  taxonomy; `sla_target_rate` in `config/workflow.yaml`.
- Tests: `test_analytics.py`, `test_reports.py`, frontend client tests, history reproducibility.
- Docs: `docs/weekly/WEEK_3_4.md`; ROADMAP Weeks 3–4 ticked; README, ARCHITECTURE, POPIA, DATA updated.

### Fixed
- Demo history dropped first-response times (the column only arrived in Week 7); now kept.
- Demo history started "24 months before today", so documented results changed with the date it was
  generated. It now starts on a fixed date (25 Oct 2024) and reproduces the documented January 2026
  backtest exactly. README/FORECASTING/WEEK_5 now quote that stable backtest (22% vs 30%).
- Forecasting model limited to one thread: after one forecast in a process, later forecasts in
  another thread (every API request) were up to 4x slower on 2 cores. Results are identical.

## [week-7.1] 2026-10-28: Audit fixes (Weeks 1–7 review)

### Fixed
- `scripts/demo_week6.py` crashed since Week 7 (staff endpoints need a login). It now creates
  the same demo staff accounts as Week 7 and logs in as the right person for each step;
  needs `--password` or `DEMO_STAFF_PASSWORD`.
- Privacy: the public status lookup (`GET /tickets/by-reference/{ref}`) no longer returns the
  category or urgency. References are sequential and guessable, so a stranger could learn that
  a learner-welfare ticket was opened today.
- Replaced the deprecated Streamlit `use_container_width` on the logout and hand-over buttons.

### Added
- `tests/test_demo_scripts.py`: runs both demo scripts end to end so they cannot break silently.
- Test that a guessed reference reveals nothing sensitive.

### Docs
- Week 2 roadmap items ticked (delivered in Week 6). Demo instructions updated for `--password`
  and the staff login. POPIA access table updated.

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
