# SchoolConnect — 8-Week Roadmap

One platform, built progressively. Tick each box only when it is built, tested and documented.

> **Schedule change (Week 5):** the bootcamp moved straight from Week 1 to Week 5, so Weeks 2–4
> were skipped. Their items stay below as optional backlog. What later weeks depend on is folded
> in: Week 5 adds its own history charts, and Week 6 starts with a minimal response generator.

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

## Week 2 — Automated Response Generation *(skipped; optional backlog)*
**Outcome:** the system classifies AND responds.

- [ ] `config/school_info.yaml` — the ONLY source of facts (details, hours, term dates, exemption docs, admissions steps, contacts)
- [ ] Response templates per category
- [ ] LLM generation grounded only in templates + school_info, in the parent's language
- [ ] Tone control: formal, friendly, urgent
- [ ] Template-only fallback without an LLM
- [ ] Responses table (draft, approved, sent; edited_by)
- [ ] Staff review / edit / approve before sending
- [ ] Welfare replies: acknowledgement only + human follow-up
- [ ] Endpoints: generate, edit, approve response
- [ ] UI: suggested-reply panel in staff inbox; instant acknowledgement on parent page
- [ ] Tests: no invented facts (dates/amounts must appear in school_info), tone differences, language matching, fallback

## Week 3 — Data Tracking & Analytics Dashboard *(skipped; history charts now in Week 5)*
**Outcome:** measurable business insights.

- [ ] `ticket_events` table (status changes, assignments, responses)
- [ ] Metrics: volume over time; by category, grade, language, urgency; first-response time; resolution time; open backlog; repeat contacts; unanswered tickets older than SLA
- [ ] Streamlit dashboard page with plotly charts, date + category filters
- [ ] AI weekly insights from computed numbers only (deterministic template fallback), no personal data
- [ ] Tests for every metric

## Week 4 — Business Reporting Automation *(skipped; optional backlog)*
**Outcome:** end-to-end reporting automation.

- [ ] Weekly PDF (reportlab): executive summary, key metrics, charts, top issues, wins & concerns
- [ ] Versions: principal/SGB (whole school) and per department / staff role
- [ ] Endpoints: generate, list, download reports
- [ ] Reports page in UI
- [ ] Protected `/jobs/weekly-report` endpoint for scheduling
- [ ] Reports stored so past weeks can be downloaded

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

- [ ] Minimal response generator first (Week 2 was skipped): grounded in `config/school_info.yaml`, tone control, template fallback, staff approval, welfare = acknowledgement only
- [ ] `app/privacy/pii.py`: SA ID (13 digits + Luhn), SA phones (0xx / +27), emails, names from name fields
- [ ] Masker applied before every LLM call and in all logs
- [ ] `ai_audit_log` table: timestamp, feature, method/model, masked input hash, output, guardrails, human override
- [ ] UI transparency notes: "AI-suggested", confidence, reason
- [ ] Bias/fairness: accuracy + response times by language and grade; flag gaps over threshold
- [ ] Prompt-injection test suite
- [ ] Risk evaluation PDF (risks, incidents, overrides, fairness)
- [ ] `docs/POPIA.md` (data, purpose, retention, access control, data subject rights)
- [ ] Retention clean-up job

## Week 7 — Workflow Automation & System Integration
**Outcome:** a fully integrated automation system.

- [ ] Staff table with roles; login with hashed passwords + token auth; staff endpoints/pages protected; parent page public
- [ ] Auto-assignment by category, role, workload
- [ ] SLAs per urgency; protected `/jobs/escalate` (e.g. class_teacher → deputy_principal)
- [ ] Notifications via SMTP or Resend behind `NOTIFY_MODE`; `dry_run` default writes to outbox table
- [ ] Parent status updates by reference; staff assignment + escalation alerts
- [ ] Fee exemption approval workflow: submitted → finance clerk review → principal approval → parent notified
- [ ] UX polish: consistent styling, mobile-friendly, empty states, helpful errors

## Week 8 — Deployment, Optimisation & Industry Showcase
**Outcome:** deployed platform and portfolio.

- [ ] Supabase Postgres, FastAPI on Vercel, Streamlit Community Cloud, scheduled jobs (Vercel Cron or GitHub Actions)
- [ ] Production seeded with demo data; `scripts/smoke_test_prod.py`
- [ ] Optimisation: DB indexes, safe caching, cold-start check, final classifier evaluation rerun
- [ ] `docs/TECHNICAL.md`, `docs/USER_GUIDE.md`, `docs/DEPLOYMENT.md`, `docs/BUSINESS_CASE.md`
- [ ] 10-minute panel presentation outline
- [ ] Portfolio README: pitch, live links, screenshots, features by week, stack, how to run, evaluation results, what I learned
