# SchoolConnect architecture

## Target system (all 8 weeks)

Solid boxes with a ✅ exist now. The other boxes are planned for the week shown.

```mermaid
flowchart LR
    subgraph Users
        P[Parent<br/>web form / email / WhatsApp gateway]
        S[School staff]
        PR[Principal & SGB]
    end

    subgraph Frontend["Streamlit frontend (Community Cloud)"]
        F1["✅ Send a message"]
        F2["✅ Staff inbox"]
        F3["✅ Overview"]
        F4["W3 Analytics dashboard"]
        F5["W4 Reports"]
        F6["✅ W5 Forecast"]
        F7["✅ W7 Staff login, My work,<br/>Fee exemptions"]
    end

    subgraph API["FastAPI backend (Vercel)"]
        A1["✅ Tickets API<br/>/tickets /stats /taxonomy"]
        A2["✅ W1 Classifier<br/>rules + LLM + safety guardrails"]
        A3["✅ W6 Response generator<br/>templates + LLM, grounded"]
        A4["W3 Analytics & insights"]
        A5["W4 PDF reports"]
        A6["✅ W5 Forecasting<br/>pandas + scikit-learn"]
        A7["✅ W6 PII masker + AI audit log"]
        A8["✅ W7 Workflow: assignment,<br/>SLA escalation, notifications,<br/>fee exemption approvals"]
        A9["✅ W7 Signed inbound webhook"]
        J["✅ /jobs/* endpoints"]
    end

    subgraph Data
        DB[("✅ Database<br/>SQLite local / Supabase Postgres")]
        CFG["✅ app/taxonomy.py<br/>W2 config/school_info.yaml<br/>W5 config/school_calendar.yaml"]
    end

    LLM["LLM provider (optional)<br/>Anthropic Claude / Gemini"]
    CRON["W8 Scheduler<br/>Vercel Cron / GitHub Actions"]
    MAIL["✅ W7 Email (SMTP)<br/>dry_run outbox by default"]

    P --> F1
    P -.gateway.-> A9
    A9 --> A1
    S --> F2
    PR --> F5
    F1 & F2 & F3 & F4 & F5 & F6 -->|HTTP only| A1
    A1 --> A2
    A2 -->|message text only| LLM
    A3 -->|"W6: masked text only"| LLM
    A2 --- CFG
    A3 --- CFG
    A1 --> DB
    A4 & A5 & A6 & A8 --> DB
    CRON --> J
    J --> A5 & A8
    A8 --> MAIL
    A7 -.wraps every LLM call.-> LLM
```

## What exists now (end of Week 1)

```mermaid
flowchart TD
    M[Parent message] --> EP["POST /tickets"]
    EP --> CM["classify_message()<br/>app/classifier/service.py"]
    CM --> Q{"LLM configured<br/>and key present?"}
    Q -- yes --> L["llm.py<br/>strict JSON, message text only"]
    L -- "valid JSON" --> G
    L -- "error / timeout / refusal / bad JSON" --> R
    Q -- "no (default)" --> R["rules.py<br/>keywords, language, urgency"]
    R --> G["Safety guardrails<br/>(can only RAISE urgency)"]
    G --> RES["ClassificationResult<br/>category, urgency, language,<br/>routed role, confidence, reason"]
    RES --> DB[("tickets table<br/>reference SC-YYYYMMDD-XXXX")]
    DB --> INBOX["Staff inbox<br/>(filters, status changes)"]
    RES --> ACK["Parent sees reference,<br/>topic and urgency<br/>+ 10111 / 112 if critical"]
```

### Components

| Part | File(s) | Responsibility |
|---|---|---|
| Taxonomy | `app/taxonomy.py` | Single source of truth: categories, routed roles, multilingual keywords, urgency, languages, statuses, safety keywords |
| Settings | `app/config.py` | Reads `.env` / environment (pydantic-settings) |
| Database | `app/db.py`, `app/models.py` | SQLAlchemy engine/session; `Ticket` table |
| Data access | `app/crud.py` | Create/list/filter tickets, references, status changes, stats |
| API schemas | `app/schemas.py` | Pydantic validation; allowed values built from the taxonomy |
| Rules classifier | `app/classifier/rules.py` | Keyword scoring, language detection, urgency words, safety term detection |
| LLM classifier | `app/classifier/llm.py` | Prompt built from the taxonomy, strict JSON, validation; any failure returns `None` |
| Orchestration | `app/classifier/service.py` | LLM → rules fallback → guardrails |
| API | `app/main.py` | FastAPI endpoints, CORS, optional API key |
| Frontend | `frontend/` | Streamlit pages; `api_client.py` is the only link to the backend |
| Scripts | `scripts/seed_db.py`, `scripts/evaluate_classifier.py` | Demo data, evaluation report |

### Safety guardrails (applied to rules AND LLM output)

| ID | Trigger | Effect |
|---|---|---|
| G1 | Critical safety term in the raw text (abuse, missing child, weapon, self-harm…) | urgency → `critical`, category → `learner_welfare`, routed to deputy principal, `needs_human` |
| G2 | Wellbeing term (bullying, injury, scared…) | urgency → at least `high`, `needs_human`; category unchanged |
| G3 | Category is `learner_welfare` | urgency → at least `high`, `needs_human` |
| G4 | Confidence < 0.35 | `needs_human` (a person checks the category) |

Guardrails look at the **original message**, so an LLM (or a prompt-injection
attempt inside the message) cannot talk its way past them.

### API endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health` | public | Liveness + active AI provider |
| GET | `/taxonomy` | public | Categories, urgency, languages, statuses, roles, grades |
| POST | `/classify` | public | Classify only, nothing saved |
| GET | `/stats` | public | Counts only, no personal data |
| GET | `/tickets/by-reference/{ref}` | public | Parent progress check: status only, no message or personal data |
| POST | `/tickets` | API key* | Create + classify a ticket |
| GET | `/tickets` | API key* | List with filters: status, category, urgency, language, routed_role, needs_human, search |
| GET | `/tickets/{id}` | API key* | Full ticket (staff) |
| PATCH | `/tickets/{id}/status` | API key* | Change status (sets/clears `resolved_at`) |

\* Only enforced when `API_KEY` is set. The Streamlit server holds the key; parents never see it.

### Data model (Week 1)

`tickets`: id, reference (unique), message, parent_name, parent_contact,
learner_grade, channel, category, urgency, language, routed_role, confidence,
method, needs_human, safety_flag, reason, status, created_at, updated_at, resolved_at.

### Key design decisions

- **Rules first, LLM optional.** The app is fully usable offline and in CI. The LLM can improve accuracy but is never required.
- **Only the message text reaches the LLM.** Name, contact and grade are stored but never sent. (Week 6 adds PII masking of the text itself.)
- **Strict, validated JSON.** Claude is called with a JSON-schema output format. Every field is checked against the taxonomy, and anything invalid falls back to rules.
- **The official Anthropic SDK** is used for Claude. Gemini is called over plain HTTPS with `httpx` to avoid a large SDK, which matters for Vercel's function size limit.
- **Frontend over HTTP only**, so it can be deployed separately (Streamlit Cloud) from the API (Vercel).

## Week 5 additions: predictive insights

```mermaid
flowchart TB
    T[("tickets table")] --> D["data.py<br/>daily counts per category<br/>(SA time, zero-filled)"]
    C["config/school_calendar.yaml"] --> F["calendar.py<br/>daily flags: term start, exams,<br/>admissions, holidays, reports"]
    D --> E["evaluate.py<br/>rolling backtest 4 × 14 days<br/>MAE / WAPE per method"]
    F --> E
    E --> M["choose method per category<br/>ML only if ≥2% better than baselines<br/>80% range from errors"]
    M --> FO["forecast.py<br/>next 1–60 days"]
    FO --> W["workload.py<br/>hours vs capacity per role"]
    WY["config/workload.yaml"] --> W
    FO --> S["surges.py<br/>spikes + likely cause"]
    W --> I["insights.py<br/>plain-language actions (templates)"]
    S --> I
    FO --> R[("forecast_runs")]
    I --> UI["Streamlit: Forecast and workload"]
```

`app/forecasting/service.py` runs this pipeline once per forecast date and caches it; the
cache key includes the ticket count, so a new ticket triggers a fresh forecast. Endpoints only
slice the cached result.

| Part | File(s) | Responsibility |
|---|---|---|
| Calendar | `app/forecasting/calendar.py`, `config/school_calendar.yaml` | Daily yes/no flags from the (approximate) school calendar |
| Data | `app/forecasting/data.py` | Tickets → daily counts per category in South African time |
| Methods | `app/forecasting/models.py` | Same as last week, same day last year, recent average, gradient boosting |
| Backtest | `app/forecasting/evaluate.py` | Leakage-free rolling backtest, method choice, 80% ranges |
| Forecast | `app/forecasting/forecast.py` | Next 1–60 days per category and in total |
| Workload | `app/forecasting/workload.py`, `config/workload.yaml` | Hours needed vs available per role; busy-week and staff scenarios |
| Spikes | `app/forecasting/surges.py` | Days ≥ 1.5× a normal day, with cause and extra hours |
| Insights | `app/forecasting/insights.py` | Template recommendations (cannot invent facts) |
| Orchestration | `app/forecasting/service.py` | Pipeline, cache, API slices, stored runs |
| History | `app/synthetic.py`, `scripts/generate_history.py` | Synthetic demo history |

### Week 5 endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/analytics/history` | API key* | Actual tickets per day (charts) |
| GET | `/forecast` | API key* | Forecast rows with 80% range, method used; actuals in backtest view |
| GET | `/forecast/workload` | API key* | Hours and utilisation per role, daily and weekly; `staff=admin_clerk:2` scenario |
| GET | `/forecast/surges` | API key* | Expected spikes with likely cause |
| GET | `/forecast/insights` | API key* | Plain-language recommendations |
| GET | `/forecast/evaluation` | API key* | Backtest accuracy per method and category |
| POST | `/jobs/refresh-forecast` | X-Jobs-Token | Recompute and store a forecast run (for the Week 8 scheduler) |

All forecast endpoints accept `as_of=YYYY-MM-DD` (a past date gives the backtest view) and `days` (1–60).

### Data model (Week 5)

`forecast_runs`: id, created_at, as_of, horizon_days, chosen_models (JSON), metrics (JSON), forecast (JSON).
The forecaster reads only `tickets.created_at` and `tickets.category`; no personal data.


## Week 6 additions: AI risk & compliance layer

```mermaid
flowchart TB
    M["Parent message<br/>(+ name, contact)"] --> PII["privacy/pii.py<br/>mask IDs, phones, emails,<br/>long numbers, known names"]
    M --> RULES["rules + safety guardrails<br/>(local, ORIGINAL text)"]
    PII --> LLM["optional AI<br/>(masked text only)"]
    LLM --> RULES
    RULES --> T[("tickets")]
    RULES --> A[("ai_audit_log<br/>hash of masked input,<br/>guardrails, PII counts")]
    T --> D["responses/generator.py<br/>template from school_info.yaml"]
    D -->|welfare / safety| ACK["acknowledgement only<br/>(never sent to an AI)"]
    D -->|AI configured| RW["AI rewrite<br/>in parent's language"]
    RW --> G{"grounding check:<br/>new number, email,<br/>link, placeholder?"}
    G -- yes --> D
    G -- no --> R
    ACK --> R[("responses: draft")]
    D --> R
    R --> S["staff edit + approve"]
    S --> A
    C["staff correction"] --> RULES
    C --> A
    A --> F["risk/fairness.py<br/>by language and grade"]
    A --> SUM["risk/summary.py"]
    INJ["risk/injection.py<br/>prompt-injection suite"] --> SUM
    F --> SUM
    SUM --> PDF["risk/report.py → PDF"]
    T --> RET["privacy/retention.py<br/>anonymise old resolved tickets"]
```

| Part | File(s) | Responsibility |
|---|---|---|
| PII masker | `app/privacy/pii.py` | Masks SA IDs (Luhn), phones, emails, long numbers, known names; log-record redaction |
| Retention | `app/privacy/retention.py` | Anonymise resolved tickets older than `RETENTION_DAYS` (dry run by default) |
| Audit | `app/audit.py`, `ai_audit_log` | One row per AI decision or human action; no raw personal data |
| Reply templates | `app/responses/templates.py`, `config/school_info.yaml` | Facts and three tones; acknowledgement-only text for welfare |
| Reply generator | `app/responses/generator.py`, `app/llm_text.py` | Optional AI rewrite with masked input and a grounding check |
| Corrections | `crud.correct_classification` | Staff override, guardrails re-applied, audit row |
| Fairness | `app/risk/fairness.py` | Accuracy, waiting time, correction rate by language and grade band |
| Injection suite | `app/risk/injection.py`, `data/prompt_injection_cases.json` | Rules, obedient-AI simulation, tag wrapping, reply grounding |
| Risk summary / PDF | `app/risk/summary.py`, `app/risk/report.py`, `config/risk_register.yaml` | Counts-only summary and 3-page report |

### Week 6 endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/tickets/{id}/responses` | API key* | Draft a reply (`tone`: formal, friendly, urgent) |
| GET | `/tickets/{id}/responses` | API key* | Reply drafts for a ticket |
| PATCH | `/responses/{id}` | API key* | Staff edit a draft (logged) |
| POST | `/responses/{id}/approve` | API key* | Staff approve a reply (logged) |
| PATCH | `/tickets/{id}/classification` | API key* | Staff correct category/urgency; guardrails re-applied |
| GET | `/tickets/{id}/audit` | API key* | Audit trail for one ticket |
| POST | `/privacy/tickets/{id}/anonymise` | API key* | POPIA: remove personal data on request |
| GET | `/risk/summary` | API key* | Counts: AI decisions, guardrails, PII masked, overrides, fairness, injection, register |
| GET | `/risk/fairness` | API key* | Fairness report |
| GET | `/risk/report.pdf` | API key* | Risk evaluation PDF |
| POST | `/jobs/retention` | X-Jobs-Token | Retention run; `dry_run=true` by default |

### Data model (Week 6)

- `responses`: id, ticket_id, tone, language, body, original_body, method, acknowledgement_only,
  status (draft/approved), edited, notes, created_at, updated_at, approved_at, approved_by.
- `ai_audit_log`: id, created_at, feature, ticket_id, method, model, llm_used, fallback_reason,
  input_hash (SHA-256 of masked input), output (JSON), guardrails (JSON), pii_found (counts),
  human_override, actor.

New tables are created automatically on startup; existing tables are unchanged, so a Week 5
database keeps working.


## Week 7 additions: workflow automation & system integration

### One message, end to end

```mermaid
flowchart TB
    WEB["Parent: web form<br/>POST /tickets"] --> IN
    GW["Email / WhatsApp gateway<br/>POST /integrations/inbound-message<br/>HMAC signature + 5-min window"] --> IN
    IN["workflow/intake.py<br/>ONE path for every channel"] --> CL["W6 mask → W1 classify<br/>→ guardrails → audit row"]
    CL --> T[("tickets")]
    CL --> AS["workflow/assignment.py<br/>welfare/critical → deputy principal<br/>else least open hours in routed role"]
    AS -->|event: assigned| EV[("ticket_events")]
    AS --> OB["notify/outbox.py<br/>dry_run | smtp | not_supported"]
    OB --> OX[("outbox")]
    AS --> MW["Staff: My work / inbox<br/>SLA badge from workflow/sla.py"]
    MW -->|start / approve reply| FR["first_response_at<br/>(stops the clock)"]
    MW -->|approve reply| OB
    MW -->|resolve| OB
    CRON["Scheduler (Week 8)"] -->|"POST /jobs/escalate<br/>X-Jobs-Token"| ES["workflow/escalation.py"]
    ES -->|"overdue: one level up the chain<br/>critical 30 min: alert deputy + principal"| EV
    ES --> AU[("ai_audit_log")]
    ES --> OB
    FEE["Fees ticket"] --> FX["workflow/fee_exemption.py<br/>submitted → finance_review →<br/>principal_decision → approved/declined<br/>→ parent_notified"]
    FX --> EV & AU
    FX -->|template letter| OB
```

### Components

| Part | File(s) | Responsibility |
|---|---|---|
| Passwords | `app/auth/passwords.py` | PBKDF2-SHA256, per-user salt, iterations in the hash, `compare_digest` |
| Accounts & sessions | `app/auth/service.py` | Create staff, login with lockout (5 → 15 min), 8-hour tokens stored as SHA-256 |
| Access rules | `app/auth/access.py`, `app/auth/deps.py` | Who may see which ticket; `current_staff`, `require_roles(...)` |
| Migration | `app/db.py: migrate()` | Adds missing columns at startup (SQLite + Postgres), idempotent |
| Events | `app/workflow/events.py` | Timeline rows; `exists()` keeps jobs idempotent |
| Intake | `app/workflow/intake.py` | The one path for web + webhook messages |
| Assignment | `app/workflow/assignment.py` | Least open hours (`config/workload.yaml`), tie-break, welfare routing, reassignment |
| SLAs | `app/workflow/sla.py`, `config/workflow.yaml` | Due times on school days/office hours (Week 5 calendar); on_track/due_soon/overdue/met |
| Escalation | `app/workflow/escalation.py` | One level up per breach; critical 30-minute alert; events + audit |
| Notifications | `app/notify/outbox.py`, `app/notify/messages.py` | Outbox (dry run / SMTP); POPIA-safe staff alerts; parent letters from school facts |
| Fee exemptions | `app/workflow/fee_exemption.py`, `app/api/fees.py` | Strict state machine, role checks (403), state checks (409) |
| Inbound webhook | `app/integrations/inbound.py`, `app/api/integrations.py` | HMAC-SHA256 over `timestamp.body`, replay window |
| Routers | `app/api/auth.py`, `app/api/workflow.py`, `app/api/fees.py`, `app/api/integrations.py` | Keep `main.py` small |
| Frontend | `frontend/auth.py`, `pages/2_My_work.py`, `pages/4_Fee_exemptions.py` | Login, role guard, quick actions, approval queues |

### Access from Week 7

Every endpoint marked "API key*" in the Week 1, 5 and 6 tables now **also needs a staff login**
(`Authorization: Bearer <token>`), and only returns tickets that person may see:

| Role | Tickets | Forecast & risk | Fee steps |
|---|---|---|---|
| Principal | all | yes | final decision, letter |
| Deputy principal | own role, assigned to them, **all welfare/safety** | yes | – |
| Finance clerk | own role (fees) or assigned, never welfare | no | review, checklist, recommendation, letter |
| Admin clerk / class teacher / IT support | own role or assigned, never welfare | no | – |
| Parent (no login) | `POST /tickets`, `GET /tickets/by-reference/{ref}` (status + reply status only) | no | – |

### Week 7 endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | Email + password → 8-hour bearer token (423 when locked) |
| POST | `/auth/logout` | staff | End this session |
| GET | `/auth/me` | staff | Who am I |
| GET | `/staff` | staff | Colleagues (for reassignment) |
| GET | `/workflow/my-work` | staff | My open tickets, overdue first, with SLA |
| GET | `/tickets/{id}/events` | staff (visible ticket) | Timeline |
| POST | `/tickets/{id}/assign` | staff (visible ticket) | Reassign (welfare only to senior staff) |
| GET | `/tickets/{id}/outbox` | staff (visible ticket) | Notifications and their status |
| POST | `/tickets/{id}/fee-exemption` | staff (visible fees ticket) | Start a request |
| GET | `/fee-exemptions`, `/fee-exemptions/{id}` | finance clerk, principal | Queues |
| POST | `/fee-exemptions/{id}/start-review` | finance clerk | submitted → finance_review |
| PUT | `/fee-exemptions/{id}/checklist` | finance clerk | Tick documents |
| POST | `/fee-exemptions/{id}/finance-decision` | finance clerk | Recommend approve/decline → principal_decision |
| POST | `/fee-exemptions/{id}/principal-decision` | principal | approved / declined |
| POST | `/fee-exemptions/{id}/notify-parent` | finance clerk, principal | Letter → parent_notified |
| POST | `/integrations/inbound-message` | HMAC signature | Ticket from an email / WhatsApp gateway |
| POST | `/jobs/escalate` | X-Jobs-Token | Escalate overdue tickets; critical alerts |

`TicketOut` now includes `assigned_to`, `first_response_at`, `escalation_level` and `sla`;
`ResponseOut` includes `delivery_status`; `TicketPublic` includes `reply_status`.

### Data model (Week 7)

- `staff`: id, name, email (unique), role, active, password_hash, failed_logins, locked_until, created_at.
- `staff_sessions`: id, token_hash (SHA-256, unique), staff_id, expires_at, created_at.
- `ticket_events`: id, ticket_id, type, from_value, to_value, actor, created_at.
- `outbox`: id, recipient, channel, kind, subject, body, ticket_id, response_id, status
  (dry_run / sent / failed / not_supported), error, created_at, sent_at.
- `fee_exemptions`: id, ticket_id (unique), status, checklist (JSON), finance_decision, finance_note,
  finance_by, finance_at, principal_decision, principal_by, principal_at, decline_reason, created_at.
- `tickets` gains: assigned_to, first_response_at, escalation_level, escalated_at (added to older
  databases by `migrate()` at startup).

### Design decisions

- **AI decisions vs workflow.** AI decisions stay in `ai_audit_log`; workflow steps go to
  `ticket_events`. Escalations and fee decisions are written to both, because they are decisions the
  principal may need to account for.
- **Idempotent escalation.** A new owner gets a fresh response window, counted from `escalated_at`.
  So a second run at the same moment finds nothing overdue, and no lock or "already done" table is
  needed. Critical alerts are sent once, checked through `events.exists()`.
- **Safe outbox by default.** `dry_run` is the default, so a demo or a test can never email a real
  parent.
- **Signed timestamp.** The webhook signs `timestamp.body`, not just the body. An old signature can
  then not be replayed with a new timestamp.
