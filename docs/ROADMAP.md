# SchoolConnect — 8-Week Roadmap

One platform, built progressively. Tick each box only when it is built, tested and documented.

> **Schedule change (Week 5):** the bootcamp moved straight from Week 1 to Week 5, so Weeks 2–4
> were skipped in the schedule. They have since been built: Week 2's reply generator as part of
> Week 6, and Weeks 3–4 (analytics dashboard and weekly reports) after Week 7.

---

## Week 1 — System Design & Ticket Classification Engine
**Outcome:** functional backend logic for request categorisation.

- [x] `docs/ARCHITECTURE.md` with a Mermaid diagram of the full target system (all 8 modules) and what exists now
- [x] `app/taxonomy.py` single source of truth: 7 categories (admissions, fees_exemptions, academic, learner_welfare, transport, it_portal, other) each with display name, description, routed role, multilingual keywords
- [x] Urgency (low, medium, high, critical), languages (en, zu, st, af, xh, unknown), statuses (new, in_progress, resolved), safety keywords
- [x] `app/schemas.py` (TicketCreate, ClassificationResult, TicketOut, TicketStatusUpdate), `config.py`, `db.py`, `models.py` (Ticket, reference `SC-YYYYMMDD-XXXX`, timestamps), `crud.py`
- [x] `data/sample_messages.csv`: 150 synthetic messages (~30% non-English/code-switched, WhatsApp style, ~12 welfare cases); documented in `docs/DATA.md`
- [x] `scripts/seed_db.py` spreads ticket dates over the last 60 days
- [x] Classifier: `rules.py` (keywords, language detection, urgency), `llm.py` (strict JSON prompt, message text only), `service.py` (LLM → rules fallback → safety guardrails that only raise urgency)
- [x] `scripts/evaluate_classifier.py` → `docs/classifier_evaluation.md` (accuracy, per-category P/R, confusion matrix, missed-critical count)
- [x] Rules accuracy ≥ 75% and ZERO missed critical cases
- [x] Endpoints: GET /health, GET /taxonomy, POST /classify, POST /tickets, GET /tickets (filters), GET /tickets/{id}, GET /tickets/by-reference/{ref}, PATCH /tickets/{id}/status, GET /stats
- [x] CORS + optional API key on write endpoints
- [x] Streamlit: "Send a message" (reference, category, urgency; critical shows 10111 / 112 notice), "Staff inbox" (filters, status change), "Overview"
- [x] CI green; tests for taxonomy, classifier, guardrails, API

## Week 2 — Automated Response Generation *(skipped in the schedule; built in Week 6)*
**Outcome:** the system classifies AND responds.

- [x] `config/school_info.yaml` — the ONLY source of facts (details, hours, exemption docs, admissions steps, contacts); term dates live in `config/school_calendar.yaml`
- [x] Response templates per category
- [x] LLM generation grounded only in templates + school_info, in the parent's language (optional; needs an API key)
- [x] Tone control: formal, friendly, urgent
- [x] Template-only fallback without an LLM
- [x] Responses table (draft, approved; edited flag, approved_by); "sent" is tracked in the Week 7 outbox
- [x] Staff review / edit / approve before sending
- [x] Welfare replies: acknowledgement only + human follow-up
- [x] Endpoints: generate, edit, approve response
- [x] UI: suggested-reply panel in staff inbox; instant acknowledgement (reference number) on parent page
- [x] Tests: no invented facts (grounding check), tone differences, language notes, fallback

## Week 3 — Data Tracking & Analytics Dashboard *(skipped in the schedule; built after Week 7)*
**Outcome:** measurable business insights.

- [x] `ticket_events` table (status changes, assignments, escalations, first responses) — built in Week 7
- [x] Metrics (`app/analytics/metrics.py`): volume by topic, urgency, language, channel, grade band, weekday and day; first-response and resolution time (median, 90th percentile, in office hours); answered within the promised time; backlog and overdue at period end; escalations; repeat contacts; all compared with the previous period
- [x] Week-by-week trends (messages, median first response, on-time rate)
- [x] Streamlit **Analytics** page: department and period filters, KPI tiles with change, trend charts, topic table, breakdowns
- [x] Weekly summary insights from computed numbers only (wins / concerns / info), no personal data
- [x] Demo history keeps first-response times; fixed start date so results are reproducible
- [x] Tests for every metric (hand-built tickets with known answers) and the insights

## Week 4 — Business Reporting Automation *(skipped in the schedule; built after Week 7)*
**Outcome:** end-to-end reporting automation.

- [x] Weekly PDF (reportlab): executive summary, key figures vs previous week, 8-week charts, topics, wins & concerns, next week's outlook (Week 5 forecast)
- [x] Versions: principal/SGB (whole school) and per department (admin, finance, teaching, welfare, IT)
- [x] Optional AI executive summary, rejected if it adds any number not in the figures; audit-logged
- [x] Endpoints: generate, list, download reports (access by role)
- [x] **Weekly reports** page in the UI
- [x] Protected `POST /jobs/weekly-reports` for scheduling (idempotent; notifies readers through the outbox) and `scripts/make_weekly_reports.py`
- [x] Reports stored (`weekly_reports` table) so past weeks can be downloaded exactly as shared

## Week 5 — Predictive Insights
**Outcome:** forward-looking decision-making.

- [x] `config/school_calendar.yaml` (APPROXIMATE, 2024–2027): terms, public holidays, admissions windows, placement offers, exams, report days
- [x] ~24 months of synthetic, calendar-driven ticket history (`scripts/generate_history.py`, `app/synthetic.py`)
- [x] 14-day (up to 60-day) daily volume forecast per category, with an 80% range
- [x] Models: same as last week (seasonal naive), same day last year, recent average with weekday/holiday factors, scikit-learn gradient boosting (calendar + day-of-week + last-year features)
- [x] Rolling backtest (MAE and WAPE, 4 × 14 days, no data leakage); ML only used where it beats the best baseline by ≥ 2%
- [x] Projected workload per staff role (`config/workload.yaml`), busy-week scenario, staff "what if" scenario, staffing suggestions
- [x] Spike detection with likely calendar cause and extra staff hours
- [x] `forecast_runs` table + protected `POST /jobs/refresh-forecast` (X-Jobs-Token)
- [x] Forecast & workload page with backtest demo view and plain-language explanation
- [x] `docs/FORECASTING.md`, `docs/forecast_evaluation.md`, `docs/weekly/WEEK_5.md`
- [x] Tests for calendar, data, models, backtest leakage, model choice, workload maths, surges, insights, API

## Week 6 — AI Risk & Compliance Layer
**Outcome:** ethical and compliance awareness layer.

- [x] Minimal response generator first (Week 2 was skipped): `config/school_info.yaml` (fictional demo school), templates per category, tone control (formal, friendly, urgent), optional AI rewrite in the parent's language, grounding check (no new numbers/emails/links/placeholders), staff edit + approve, welfare/safety = acknowledgement only and never sent to an AI
- [x] `app/privacy/pii.py`: SA ID (13 digits + real date + Luhn), SA phones (0xx / +27 / 0027), emails, long numbers, names from name fields
- [x] Masker applied before every LLM call (classification and replies) and to every log record
- [x] `ai_audit_log` table: timestamp, feature, method/model, AI used, fallback reason, masked input hash, output, guardrails, PII counts, human override, actor
- [x] UI transparency notes: "AI-suggested" / "Checked by staff", method, confidence, reason, guardrails, audit trail
- [x] Staff corrections of category/urgency (human override), guardrails re-applied so safety tickets cannot be lowered
- [x] Bias/fairness: classifier accuracy, median resolution time and correction rate by language and grade band; gaps over threshold flagged; small groups not judged
- [x] Prompt-injection test suite (`data/prompt_injection_cases.json`): rules, obedient-AI simulation, data-tag wrapping, reply grounding
- [x] Risk evaluation PDF (`GET /risk/report.pdf`) + Risk & compliance page + `config/risk_register.yaml`
- [x] `docs/POPIA.md` (data, purpose, cross-border AI, retention, access control, data subject rights)
- [x] Retention clean-up job (`POST /jobs/retention`, dry run by default) + anonymise-on-request
- [x] `scripts/demo_week6.py`, tests (185 passing), `docs/weekly/WEEK_6.md`

## Week 7 — Workflow Automation & System Integration
**Outcome:** a fully integrated automation system.

- [x] Staff table with roles; login with hashed passwords (PBKDF2, lockout) + token auth; staff endpoints/pages protected; parent page public
- [x] Least privilege: welfare tickets for deputy principal + principal only; forecast/risk for senior staff
- [x] `ticket_events` table (replaces the skipped Week 3 one) and an idempotent startup migration
- [x] Auto-assignment by category, role, workload (open hours from `config/workload.yaml`)
- [x] SLAs per urgency on school days (`config/workflow.yaml`); protected, idempotent `/jobs/escalate` (e.g. class_teacher → deputy_principal); 30-minute critical alert
- [x] Notifications via SMTP behind `NOTIFY_MODE`; `dry_run` default writes to outbox table (Resend not needed)
- [x] Parent status updates by reference; staff assignment + escalation alerts (no PII in alerts)
- [x] Fee exemption approval workflow: submitted → finance clerk review → principal approval → parent notified
- [x] Signed inbound webhook for email / WhatsApp gateways (`docs/INTEGRATIONS.md`)
- [x] UX polish: consistent styling, mobile-friendly, empty states, helpful errors
- [x] `scripts/demo_week7.py`, tests (326 passing), `docs/weekly/WEEK_7.md`

## Week 8 — Deployment, Optimisation & Industry Showcase
**Outcome:** deployed platform and portfolio.

- [x] Render Blueprint (`render.yaml`): two free web services in Frankfurt, Python 3.11 pinned, auto-deploy from `main`
- [x] Supabase Postgres via the transaction pooler (port 6543, prepared statements off, small pool); production start-up checks
- [x] Scheduled jobs on GitHub Actions: escalation, keep-warm, dry-run retention (calls), forecasts and weekly reports (run on GitHub against Supabase)
- [x] Stored, signed forecasts for today and pinned demo dates; endpoints read them first
- [x] `scripts/smoke_test_prod.py` (9 checks, PASS/FAIL + timings): 9/9 locally
- [ ] **Live:** deployed on Render + Supabase, production seeded with demo data, smoke test 9/9 against the live URLs *(waiting for the account setup in docs/DEPLOYMENT.md)*
- [x] Optimisation: measured memory and 0.1-CPU timings; 30–60× faster workload maths; lazy scikit-learn import; cached checks; no indexes needed (all queries ≤ 6 ms); evaluations re-run (January numbers unchanged)
- [x] `docs/TECHNICAL.md`, `docs/USER_GUIDE.md` (with screenshots), `docs/DEPLOYMENT.md`, `docs/BUSINESS_CASE.md`
- [x] 10-minute panel presentation (`docs/PRESENTATION.md`): slides, live demo script, backup plan, 12 Q&A
- [x] Portfolio README: pitch, live links, screenshots, features by week, results, stack, how to run (What I learned / About me: for Dikeledi to write)
- [x] `docs/weekly/WEEK_8.md`; 402 tests passing
