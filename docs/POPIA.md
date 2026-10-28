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
| Notifications | `outbox` | yes | What was sent to whom, and whether it arrived (section 7b) |
| Workflow timeline | `ticket_events` | yes | Who was assigned, status changes, escalations. No message text or contact details |
| Fee exemption decisions | `fee_exemptions` | when requested | Document checklist, recommendation, decision, decline reason |
| Staff accounts | `staff`, `staff_sessions` | yes | Name, work email, role, password **hash**, login **token hash** |

SchoolConnect does **not** ask for ID numbers, but parents sometimes type them into messages. These
are detected and masked before any external AI service sees the text (section 3).

## 2. Purpose and minimality (POPIA conditions 2 and 3)

Personal information is used only to answer the parent's request, keep learners safe, and improve
the service (statistics, forecasts, fairness checks). Forecasting and statistics use only the date
and category of each ticket. Reports contain counts only, never names or messages.

The Weeks 3–4 analytics and weekly reports also use counts and times only. "Parents who wrote more
than once" compares contact details inside the calculation, but only the **count** is kept or shown;
stored reports (`weekly_reports`) and "report ready" emails contain no names, contacts or message text.

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
- Week 7: the same clean-up runs on the ticket's **outbox** rows. The parent's email or phone
  number becomes `[REMOVED]` and personal data in the text is masked. The same happens when staff
  anonymise a ticket on request.
- Open tickets are never touched.
- Job: `POST /jobs/retention` (requires `X-Jobs-Token`), **dry run by default**. Week 8 schedules it.
- Each real run writes a `retention` row to the audit log.

## 7. Access control (condition 7: security safeguards)

Since Week 7 every staff member has their own login, so access is limited **by role**. The API
enforces this on every request; the Streamlit pages only hide what the API would refuse anyway.

| Who | Can see / do |
|---|---|
| Anyone with a reference number | Status, dates and whether a reply was sent. No message, no personal data, and no category or urgency (references are sequential and guessable, and "a learner welfare ticket today" is sensitive) |
| Principal | Every ticket; forecast and risk pages; final fee exemption decisions |
| Deputy principal | Tickets routed to or assigned to them, and **every learner-welfare / safety ticket**; forecast and risk pages |
| Finance clerk, admin clerk, class teacher, IT support | Tickets routed to their role or assigned to them. **Never** learner-welfare / safety tickets. Finance clerk: fee exemption review steps |
| Analytics & weekly reports (Weeks 3–4) | Principal: every department. Deputy principal: whole school and learner welfare. Everyone else: their own department only. Counts only |
| Scheduler (`JOBS_TOKEN`) | Can trigger jobs only |
| Gateway (`INBOUND_SECRET`) | Can create tickets only, with a signed request (`docs/INTEGRATIONS.md`) |

How it is protected:

- **Hidden tickets answer `404`.** A ticket someone may not see gets `404`, not `403`, so its
  existence is not revealed.
- **Welfare tickets stay with senior staff.** They are assigned automatically to the deputy
  principal, and cannot be reassigned to anyone else except the principal.
- **Passwords.** They are stored only as PBKDF2-SHA256 hashes, with a salt per user and 600 000
  iterations. After 5 wrong passwords the account is locked for 15 minutes. A wrong email and a
  wrong password give the same message.
- **Login tokens.** A token lasts 8 hours. The database stores only its SHA-256 hash, so a copy of
  the database cannot be used to log in. A deactivated account loses access immediately.
- **Accountability.** Every action records the **logged-in** staff member. Nobody can type someone
  else's name.
- **Secrets.** Secrets live in `.env`, never in git. Demo passwords are typed at a prompt or passed
  as a command argument, never stored.
- **Hosting.** Production uses Supabase Postgres (encrypted at rest) over TLS.

## 7b. Notifications: what leaves the school, and to whom

All notifications go through the `outbox` table, which records the recipient, the text, and whether
the message was sent (`dry_run`, `sent`, `failed` or `not_supported`).

- **Default is dry run.** `NOTIFY_MODE=dry_run` records but sends nothing. Real email needs
  `NOTIFY_MODE=smtp` and the school's own SMTP account.
- **What parents receive:**
  - the reply a staff member **approved**
  - a "resolved" notice
  - fee exemption letters

  Letters are templates built from `config/school_info.yaml` only. They go to the contact the parent
  gave, and only email is supported. Phone numbers are recorded as `not_supported` and staff phone
  the parent.
- **What staff alerts contain.** Alerts for assignment, escalation and new or unacknowledged
  critical tickets contain only the **reference, category, urgency and response deadline**. They
  never include the message text, the parent's name or contact details, or the learner's grade.
  Email gets forwarded and read on shared phones, so the details stay behind the login.
- **Welfare alerts contain only the reference:** *"New learner welfare ticket SC-…, open
  SchoolConnect."* There is no category text, urgency or deadline.
- **What the timeline records.** The `ticket_events` timeline records *that* a notification was
  queued and its status. It never records the address or the text.
- **SMTP errors are masked** before they are stored, because they can echo an email address back.

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
- [ ] Set `API_KEY` and `JOBS_TOKEN`; schedule the retention and escalation jobs
- [ ] Create one staff account per person (`scripts/create_staff.py`); deactivate leavers at once
- [ ] Keep `NOTIFY_MODE=dry_run` until the SMTP account and the reply templates have been checked
- [ ] If a gateway is connected, set a long random `INBOUND_SECRET` and share it only with that system
- [ ] Review `config/risk_register.yaml` each term
- [ ] First-language speakers review the isiZulu, Sesotho, Afrikaans and isiXhosa keywords
