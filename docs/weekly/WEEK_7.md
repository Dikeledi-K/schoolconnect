# Week 7 – Workflow Automation & System Integration

**Sprint goal:** connect the modules into one automated flow.
**Feature built:** Workflow Automation & Integration Module.
**Outcome:** a fully integrated automation system. A parent message flows end to end with no
manual copying:

1. received
2. classified
3. assigned to a person
4. reply drafted
5. reply approved
6. parent notified
7. escalated automatically if overdue

Every step is logged.

## What was built

1. **Staff accounts and login.**
   - **Passwords:** stored as PBKDF2-SHA256 hashes, using the standard library only, with a salt per
     user and 600 000 iterations. Comparisons use `compare_digest`.
   - **Lockout:** an account is locked for 15 minutes after 5 failed logins.
   - **Sessions:** bearer tokens last 8 hours, and only their SHA-256 hash is stored.
   - **Endpoints:** `POST /auth/login`, `/auth/logout`, `GET /auth/me`.
   - **Accounts:** created with `scripts/create_staff.py`; the password is typed at a hidden prompt.
2. **Least privilege (POPIA).**
   - Staff see tickets routed to their role or assigned to them.
   - Learner-welfare and safety tickets are visible only to the deputy principal and the principal.
   - The forecast and risk pages are for those two roles only.
   - A hidden ticket answers `404`, so its existence is not revealed.
   - Every event and audit row records the *logged-in* person; the typed-in name box is gone.
3. **Ticket events** (`ticket_events`): assignments, status changes, first response, escalations,
   critical alerts, notifications and fee steps. This is the events table from the skipped Week 3.
4. **Startup migration** (`app/db.py: migrate()`).
   - Adds missing columns with `ALTER TABLE … ADD COLUMN`, on SQLite and Postgres.
   - Idempotent, so running it twice is harmless.
   - Tested on a database with the Week 6 schema, and run on the real local Week 6 database.
5. **Auto-assignment.**
   - A ticket goes to the active staff member in the routed role with the **least open work in
     hours**, using the same handling times as the Week 5 forecast. Ties go to whoever has had fewest
     assignments.
   - Welfare and critical tickets always go to the deputy principal, or the principal if there is no
     deputy.
   - If nobody in the role is active, the ticket waits in the role queue and the reason is logged.
6. **SLAs** (`config/workflow.yaml`, `app/workflow/sla.py`).
   - The targets match the promises in `school_info.yaml`:

     | Urgency  | First response due |
     |----------|--------------------|
     | critical | 1 clock hour       |
     | high     | 1 school day       |
     | medium   | 2 school days      |
     | low      | 5 school days      |

   - School days skip weekends and the public holidays in the Week 5 calendar, and the clock counts
     office hours (07:30 to 15:30).
   - Each ticket's status is shown as on track, due soon, overdue or met.
7. **Escalation job** (`POST /jobs/escalate`, X-Jobs-Token).
   - An overdue ticket moves one level up the chain: teacher → deputy → principal; clerks and IT →
     principal.
   - The new owner is notified, and the job logs an event and an audit row.
   - The new owner's clock restarts, which makes the job **idempotent**.
   - A critical ticket nobody has acknowledged after 30 minutes alerts the deputy principal *and* the
     principal.
   - It runs in a single request with no background threads, ready for a scheduler (Week 8:
     GitHub Actions calls it every 15 minutes in school hours).
8. **Notifications** through an **outbox** table.
   - `NOTIFY_MODE=dry_run` (the default) only records the notification; `smtp` sends real email.
   - Phone-number contacts are recorded as `not_supported`, and the inbox tells staff to phone the
     parent.
   - Parents get the approved reply itself, and a message when the ticket is resolved.
   - Staff get alerts on assignment, escalation and new critical tickets. Alerts carry the reference,
     category, urgency and due time only. Welfare alerts carry *only* the reference.
   - The retention job also anonymises outbox rows.
9. **Fee exemption workflow** (`fee_exemptions`): a strict state machine.
   - **Steps:**
     1. submitted
     2. finance review: the clerk ticks the checklist from `school_info.yaml`
     3. finance recommendation
     4. principal decision
     5. parent letter, a template built from school facts only
   - **Role rules:** only the finance clerk does the finance steps, and only the principal makes the
     final decision.
   - **Required information:** declining needs a reason, and recommending approval needs every
     document.
   - **Errors and logging:** a wrong role gets `403` and a wrong state gets `409`. Every step is an
     event and an audit row.
10. **Signed inbound webhook** (`POST /integrations/inbound-message`).
    - Email forwarders and WhatsApp gateways can create tickets, signed with HMAC-SHA256 over
      `timestamp.body` using `INBOUND_SECRET`.
    - Requests older than 5 minutes are refused.
    - These tickets take the same path as the web form. See `docs/INTEGRATIONS.md`.
11. **Frontend.**
    - Staff log in; the token is kept in this browser session only. There is a logout button in the
      sidebar.
    - New **My work** page: overdue first, SLA badges, and Start / Resolve / Hand over buttons.
    - New **Fee exemptions** page: one queue per step, and buttons only for the right role.
    - **Staff inbox:** shows the assignee, response-time status, timeline, reassignment, and whether a
      reply was "sent" or "queued (dry run)".
    - **Parent page:** "Check my message" in plain words, shown as cards with no tables, so it works
      on a phone.
    - Empty states and friendly errors throughout.
12. `scripts/demo_week7.py` and **141 new tests (326 in total)**. All existing tests still pass
    without deleting an assertion; the test fixtures now log in.

## Curriculum mapping

| Curriculum item | Where |
|---|---|
| Automate repetitive workflows | One intake path, auto-assignment, SLA timers, escalation job, outbox notifications |
| Integrate modules into one system | Classifier (W1), workload model (W5), masking/audit/replies (W6) and the calendar all feed the workflow |
| System integration with other platforms | Signed inbound webhook, SMTP email, scheduler-ready `/jobs/*` endpoints |
| Approval workflows | Fee exemption state machine with role checks and an audit trail |
| Alignment: secure, ethical automation | Least-privilege access, POPIA-safe alerts, humans approve every reply and decision |

## Grading rubric mapping

**Technical skills (40%): working, integrated, tested automation**

| Evidence |
|---|
| One message goes from received to escalated with no manual step, shown live in the demo |
| SLA maths tested across a weekend, after hours, and the Easter 2026 public holidays |
| Escalation tested for idempotency (same breach twice = one escalation) |
| All 30 fee-exemption transitions tested, valid and invalid; 403 and 409 tested for every role |
| HMAC signature, tampering, replay (old and future timestamps) and a published test vector |
| Migration tested on a Week 6 schema and run on a real Week 6 database |

**Professional skills (60%): process design, security, clarity**

| Evidence |
|---|
| Response-time targets come from the school's own promises to parents, and a test keeps them in step |
| Staff alerts contain no message text or parent details; welfare alerts carry only the reference |
| `docs/INTEGRATIONS.md` gives another team everything it needs: headers, codes, example code, test vector |
| Honest limits below; the dry-run default means the demo can never email a real parent by accident |

## 5-minute demo script: one message, end to end

Setup:

```
python scripts/generate_history.py --reset
python scripts/demo_week7.py --password <demo password>
uvicorn app.main:app
streamlit run frontend/Home.py
```

1. **(30s) The problem.** "Before Week 7, someone still had to notice a message, decide who should
   handle it, chase it when it went quiet, and copy the reply into an email. Today that is automatic."
2. **(60s) A parent writes.** On *Send a message*, a parent with an email address asks about Grade 1
   admission and gets a reference number. Log in as **Ms L. Khumalo (admin clerk)**. *My work* shows
   it straight away: assigned to her because she has the least open work, with a green
   "16 h left" badge.
3. **(60s) Reply and notify.** In the *Staff inbox*, open the ticket. The timeline shows *Assigned
   (auto: least open work)* and *Notification: staff_assigned*. Draft a friendly reply and press
   **Approve and send**: it shows *Queued (dry run)*. The timeline gains *First response* and
   *Notification: parent_reply*. Back on the parent page, *Check my message* says the school has
   replied, with no personal data shown.
4. **(45s) Nobody answers.** The ticket SC-…-0012 was back-dated by the demo script. Log in as
   **Mr T. Mokoena (deputy)**: it sits in his *My work* marked *escalated 1×*. The timeline shows
   *Escalated: Class Teacher, overdue … → Mr T. Mokoena*. "The job ran twice; it escalated once."
5. **(45s) Child safety and privacy.** The bullying ticket went straight to the deputy. Log in as the
   admin clerk again: the welfare ticket is not in her inbox at all. Show the welfare alert text:
   *"New learner welfare ticket SC-…, open SchoolConnect."*, and nothing else.
6. **(40s) Fee exemption.** As **Mrs N. Dlamini (principal)**, open *Fee exemptions → Principal*.
   Finance recommends approval with all 3 documents ticked. Approve it, then *Tell the parent →
   Send the letter*. The timeline lists all five steps with who did each.
7. **(20s) Integration.** "WhatsApp messages arrive through a signed webhook. Here is the WhatsApp
   ticket the demo sent; a forged or replayed request gets a 401."

## Known limitations

- **No SMS or WhatsApp replies yet.** Phone contacts are marked `not_supported` and staff must phone
  the parent.
- **Refreshing logs you out.** A browser refresh or a pasted URL starts a new Streamlit session, so
  staff log in again. The token is never written to disk or the URL, on purpose.
- **Webhook repeats.** An identical webhook request repeated *within* 5 minutes would create a second
  ticket. A list of signatures already seen is Week 8 backlog.
- **Approximate calendar.** The office-hours clock uses the approximate Week 5 calendar and a single
  set of office hours. Half days and school-specific closures are not modelled.
- **Simple workload estimate.** Auto-assignment uses average handling times, not each person's real
  speed or leave days. Mark someone *inactive* while they are away.
- **No password reset screen.** An admin runs `create_staff.py`, or deactivates and recreates the
  account.
- **Escalation needs a scheduler.** It only runs when `/jobs/escalate` is called; Week 8 schedules it.

## Retrospective questions

1. The escalation clock restarts for each new owner. Is that fair to the parent, who has now waited
   longer? What would you show the principal so that a ticket is not "on track" again after two
   misses?
2. Welfare alerts say almost nothing, so they are safe to forward but less useful. Where is the right
   balance between privacy and helping a deputy principal act quickly?
3. Which manual step is still left in the flow from received to resolved, and what would it take to
   automate it safely?
