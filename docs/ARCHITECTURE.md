# SchoolConnect architecture

## Target system (all 8 weeks)

Solid boxes with a ✅ exist now. The other boxes are planned for the week shown.

```mermaid
flowchart LR
    subgraph Users
        P[Parent<br/>web form / WhatsApp later]
        S[School staff]
        PR[Principal & SGB]
    end

    subgraph Frontend["Streamlit frontend (Community Cloud)"]
        F1["✅ Send a message"]
        F2["✅ Staff inbox"]
        F3["✅ Overview"]
        F4["W3 Analytics dashboard"]
        F5["W4 Reports"]
        F6["W5 Forecast"]
        F7["W7 Staff login"]
    end

    subgraph API["FastAPI backend (Vercel)"]
        A1["✅ Tickets API<br/>/tickets /stats /taxonomy"]
        A2["✅ W1 Classifier<br/>rules + LLM + safety guardrails"]
        A3["W2 Response generator<br/>templates + LLM, grounded"]
        A4["W3 Analytics & insights"]
        A5["W4 PDF reports"]
        A6["W5 Forecasting<br/>pandas + scikit-learn"]
        A7["W6 PII masker + AI audit log"]
        A8["W7 Workflow: assignment,<br/>SLA escalation, notifications,<br/>fee exemption approvals"]
        J["W4/W7 /jobs/* endpoints"]
    end

    subgraph Data
        DB[("✅ Database<br/>SQLite local / Supabase Postgres")]
        CFG["✅ app/taxonomy.py<br/>W2 config/school_info.yaml<br/>W5 config/school_calendar.yaml"]
    end

    LLM["LLM provider (optional)<br/>Anthropic Claude / Gemini"]
    CRON["W8 Scheduler<br/>Vercel Cron / GitHub Actions"]
    MAIL["W7 Email (SMTP / Resend)<br/>dry_run outbox by default"]

    P --> F1
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
