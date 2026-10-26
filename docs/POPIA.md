# POPIA: how SchoolConnect protects personal information

The Protection of Personal Information Act (POPIA, 2013) applies to any South African school that
collects information about parents and learners. This page explains what SchoolConnect collects,
why, how long it is kept, who can see it, and how parents can exercise their rights.

> This is a technical description of the system, not legal advice. Each school should have its own
> Information Officer review it and adapt the retention period and access rules to school policy.
> Learners' information is the personal information of children, which POPIA treats as needing
> extra care; the school's PAIA/POPIA manual should cover SchoolConnect.

## 1. What is collected

| Data | Where | Required? | Why |
|---|---|---|---|
| Message text | `tickets.message` | yes | To understand and answer the request |
| Parent name | `tickets.parent_name` | optional | To address the reply |
| Phone or email | `tickets.parent_contact` | optional | To reply |
| Learner grade | `tickets.learner_grade` | optional | Routing and fairness checks by grade |
| Channel | `tickets.channel` | yes | Web, WhatsApp, email |
| Classification | `tickets.category`, `urgency`, `language`… | yes | Routing, safety, statistics |
| Reply drafts | `responses` | yes | Staff review before anything is sent |
| AI audit log | `ai_audit_log` | yes | Accountability (see section 5) |

SchoolConnect does **not** ask for ID numbers, but parents sometimes type them into messages. These
are detected and masked before any external AI service sees the text (section 3).

## 2. Purpose and minimality (POPIA conditions 2 and 3)

Personal information is used only to answer the parent's request, keep learners safe, and improve
the service (statistics, forecasts, fairness checks). Forecasting and statistics use only the date
and category of each ticket. Reports contain counts only, never names or messages.

## 3. Sharing with AI services (conditions 4 and 7, section 72 cross-border transfer)

By default (`LLM_PROVIDER=rules`) **nothing leaves the school's systems**. If the school enables an
external AI (Anthropic or Google), these safeguards apply:

- **Only the message text** is sent. Name, contact and grade fields are never sent.
- The text is **masked first** (`app/privacy/pii.py`): SA ID numbers (13 digits, real birth date,
  Luhn check), SA phone numbers, email addresses, other long numbers (e.g. bank accounts), and the
  parent's own name become `[ID_NUMBER]`, `[PHONE]`, `[EMAIL]`, `[NUMBER]`, `[NAME]`.
- **Welfare and safety messages are never sent to an AI for replies**: those replies are fixed
  acknowledgements, and a person follows up.
- Child-safety guardrails run **locally on the original text**, so masking never weakens safety.

Known limit: a learner's name typed inside a message cannot be reliably detected by rules. Schools
that enable an external AI should note this in their POPIA risk assessment, or stay in rules mode.

AI providers may process data outside South Africa. Before enabling one, the school must check the
provider's data-processing terms (POPIA section 72) and record the decision.

## 4. Logs

Every log line passes through the same masker (`install_log_redaction()` in `app/main.py`). Server
access logs record only the method, path and status code, never request bodies.

## 5. Accountability: the AI audit log (condition 1)

`ai_audit_log` has one row per AI decision or human action:
classification, reply draft, staff edit, approval, correction ("human override"), anonymisation and
retention runs. Each row stores the method/model, whether an AI was used, any fallback reason, the
guardrails that fired, **counts** of personal data masked, and a **SHA-256 hash of the masked input**.
It never stores the raw message, names or contact details. This lets the school show what the AI
decided and that a person reviewed it, without creating a second copy of personal data.

## 6. Retention (condition 3: no longer than necessary)

- Setting: `RETENTION_DAYS` (default **365**).
- Rule: **resolved** tickets whose resolution is older than `RETENTION_DAYS` are **anonymised**:
  name and contact removed, personal data in the message (and its replies) masked. Category, dates,
  and urgency stay, so statistics and forecasts keep working.
- Open tickets are never touched.
- Job: `POST /jobs/retention` (requires `X-Jobs-Token`), **dry run by default**. Week 8 schedules it.
- Each real run writes a `retention` row to the audit log.

## 7. Access control (condition 7: security safeguards)

| Who | Can see |
|---|---|
| Anyone with a reference number | Only status, category, urgency and dates (no message, no personal data) |
| Staff (frontend holds `API_KEY`) | Tickets, replies, audit trail, risk page |
| Scheduler (`JOBS_TOKEN`) | Can trigger jobs only |

Week 7 adds individual staff logins so access can be limited by role. Until then the API key is
held only by the Streamlit server, never by parents. Secrets live in `.env`, never in git.
Production uses Supabase Postgres (encrypted at rest) over TLS.

## 8. Data subject rights (sections 23–25)

| Right | How |
|---|---|
| Access ("what do you hold about me?") | Staff search the inbox by name, contact or reference and share the ticket |
| Correction | Staff correct the classification (logged) or the parent sends a new message |
| Deletion / objection | Staff use **Privacy (POPIA) → Anonymise this ticket** in the inbox (`POST /privacy/tickets/{id}/anonymise`), recorded in the audit log |

## 9. Security incidents (section 22)

If personal data may have been exposed (e.g. a leaked API key), the Information Officer must notify
the Information Regulator and affected parents as soon as reasonably possible. Rotate `API_KEY`,
`JOBS_TOKEN` and any AI keys, and use the audit log to establish what was processed.

## 10. Checklist before real use

- [ ] Replace `config/school_info.yaml` (fictional demo school) with real school details
- [ ] Information Officer reviews this page and sets `RETENTION_DAYS`
- [ ] Decide whether to enable an external AI; if so, check the provider terms (section 72)
- [ ] Set `API_KEY` and `JOBS_TOKEN`; schedule the retention job
- [ ] Review `config/risk_register.yaml` each term
- [ ] First-language speakers review the isiZulu, Sesotho, Afrikaans and isiXhosa keywords
