# SchoolConnect business case

**One line:** SchoolConnect gives a South African public school's office an AI help desk that
answers parents faster, gets each message to the right person automatically, and gives the office
back about **140 hours a term**, for about **R700 a month**.

> Every figure marked **(A)** is an *assumption*, stated so it can be challenged and replaced with a
> real school's numbers. Message volumes come from the project's synthetic demo data for one
> primary school; handling times come from `config/workload.yaml`.

## 1. The problem

- **January and the admissions window overwhelm the office.** In the demo data, January has 524
  messages, 2.5× December.
- **Teachers are pulled into admin** questions such as reports, meetings and marks.
- **Messages get lost** in WhatsApp groups and personal phones. Nobody knows who is handling what,
  or whether a parent got an answer.
- **Parents wait days**, then write again ("any update?"), which makes the queue longer.
- **Learner-safety messages** (bullying, abuse, a child not home) can sit in the same pile as fee
  questions.
- **Principals and SGBs have no figures**: how many messages, how fast, what is coming next term.

## 2. Who it serves

| Who | What they get |
|---|---|
| Parents (in 5 languages) | one place to ask, a reference number, a clear status, an answer on time |
| Office staff (admin and finance clerks) | their own queue, drafted replies, no copying between apps |
| Teachers | only the questions that are really theirs |
| Deputy principal | every learner-welfare case immediately, never hidden in the pile |
| Principal and SGB | weekly reports, a forecast of busy periods, a risk and POPIA report |

## 3. The solution

1. **Classifies** every message by topic, urgency and language. It works offline; an AI is
   optional.
2. **Protects children first.** Abuse, missing children, weapons and self-harm are always critical,
   go straight to the deputy principal, and always need a person.
3. **Assigns** each message to the right person with the least open work, and **escalates**
   automatically if the school's promised response time is missed.
4. **Drafts replies** from the school's own facts only. A person approves every one.
5. **Tracks and reports**: analytics, weekly PDF reports, a forecast of the next weeks' workload
   per role, and a risk and compliance report.
6. **POPIA by design**:
   - personal data is masked before any AI sees it;
   - access by role;
   - an audit log;
   - old data is anonymised.

## 4. Evidence from the demo

| Measure | Result |
|---|---|
| Classifier accuracy (150 labelled messages, 5 languages) | **96.0%**, **0 of 6** critical cases missed |
| Prompt-injection checks | **23 / 23** pass |
| January 2026 rush, forecast made on 15 Dec 2025 | forecast 421 vs actual 486 (**16% error**); 84% of days inside the 80% range |
| Admin clerk, week of 19 Jan 2026 | forecast **86%** of capacity, actual **88%**, so the school could plan help in December |
| Answered within the promised time (demo week of 19 Oct 2026) | **97%** (target 90%); median first response 3.3 office hours |
| Automated tests | **402** pass on every change |

The data is synthetic, so these numbers show the system *works as designed*, not its effect on a
real school. A pilot measures that (section 9).

## 5. Impact estimates (per school term)

**Volumes** (demo data, one primary school, 2025):
- **4,798 messages a year**, about **1,200 a term**;
- **1,116 staff hours a year** to handle them, about **279 hours a term** (handling minutes per
  topic from `config/workload.yaml`, for example fees 20 minutes, welfare 45).

| Saving | How it is worked out | Hours / term |
|---|---|---:|
| **Triage and routing** | Today someone reads each message, decides who should handle it, forwards it and keeps track: **(A) 3 minutes** per message. SchoolConnect does this automatically. 1,200 × 3 min | **60** |
| **Drafted replies** | Template drafts from school facts **(A) save 30%** of handling time on non-welfare topics (welfare is excluded; a person always handles it). (1,116 − 161 welfare hours) / 4 terms × 30% | **72** |
| **Fewer parents writing twice** | **(A) 15%** of messages today are follow-ups; reference-number checks plus "your reply" and "resolved" notices **(A) halve them**. 7.5% × 1,200 = 90 fewer messages × **(A) 8 min** | **12** |
| **Total** | | **≈ 144 hours** |

- **144 hours a term is about 3.8 weeks** of one full-time clerk (37.5 h/week), every term.
- **(A)** At R115 an hour (about R20,000 a month), that is about **R16,600 a term** or
  **R66,000 a year** of staff time, freed for admissions, fees and learners rather than inbox work.
- **Faster first responses.** Every parent gets an instant acknowledgement with a reference. Each
  message has a promised first-response time (critical 1 hour; high, medium and low 1, 2 and
  5 school days). Late tickets escalate by themselves, so nothing waits "days" unnoticed.
- **Child safety.** Welfare messages reach the deputy principal at once, with a 30-minute alert to
  the principal if nobody acknowledges a critical one.

## 6. Costs

**Now (the demo):** **R0**, because everything runs on free tiers. The trade-off is that the free
services sleep when unused and are slow (`TECHNICAL.md`).

**A real school (always on), per month:**

| Item | Price | Why |
|---|---:|---|
| Render Starter, API | $7 | always on, 512 MB, 0.5 CPU (5× the free CPU) |
| Render Starter, web | $7 | always on |
| Supabase Pro | $25 | never paused, daily backups (kept 7 days) |
| **Total** | **$39 ≈ R700** | **(A)** at R18 to the US dollar; about **R8,400 a year** |

**Optional AI**: only needed for better classification or replies in the parent's own language.
The cost per **1,000 messages**, if each message is classified and gets one reply draft:

| Provider / model | Price per million tokens (input / output) | Cost per 1,000 messages | A year (4,800 messages) |
|---|---|---:|---:|
| Rules only (default) | none | **$0** | $0 |
| Claude Haiku 5.5 | $0.10 / $0.50 | **≈ $0.67** | ≈ $3 |
| Gemini 2.5 Flash (paid tier) | $0.30 / $2.50 | **≈ $3** | ≈ $14 |
| Claude Sonnet 5.5 | $2 / $10 | **≈ $13** | ≈ $64 |
| Claude Opus 5.5 | $4 / $20 | **≈ $27** | ≈ $128 |

**(A) Tokens per message:**
- **Classification:** about 600 in and 280 out.
- **Reply rewrite:** about 900 in and 750 out.

Output includes the model's reasoning ("thinking") tokens, which are billed as output.

*Do not use Gemini's free tier for parent messages:* Google's pricing page says free-tier content
is used to improve its products, which conflicts with POPIA.

**Value against cost:** about **R66,000** of staff time a year **(A)** against about **R8,400**
running costs, so roughly **8 to 1**, before any AI.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The AI misjudges a safety message | Guardrails on the original text can only raise urgency; welfare always goes to a person; 0 of 6 critical cases missed in evaluation |
| The AI invents a fee, date or bank account | replies are built from school facts; an AI rewrite with any new number, email or link is rejected; staff approve everything |
| A personal-data leak | masking before any AI and in logs; access by role; audit log; retention anonymisation; no data leaves the school in rules mode |
| Bias against isiZulu, Sesotho, Afrikaans or isiXhosa speakers | fairness checks by language and grade on every Risk page; keywords to be reviewed by first-language speakers before real use |
| Staff do not adopt it | it removes work (drafts, routing) rather than adding it; *My work* shows only your own tickets; a short training session |
| Free-tier sleep or outages | paid tiers for a real school (section 6); daily backups on Supabase Pro |
| Parents without email | phone contacts are flagged so staff call; SMS / WhatsApp replies are the next step |

## 8. Rollout plan for a real school

1. **Weeks 1–2: set up.**
   - The school fills in `config/school_info.yaml` (its own facts), the calendar and
     `workload.yaml`.
   - The Information Officer reviews `docs/POPIA.md`.
   - Accounts are created for each staff member.
2. **Weeks 3–4: pilot with the office only.**
   - The admin and finance clerks copy WhatsApp and email messages into SchoolConnect.
   - Measure triage time and first-response time **before and after**, to replace the (A) figures.
3. **Weeks 5–8: open to parents.**
   - Share the link through the school's WhatsApp groups and newsletter.
   - Connect the school email through the signed webhook.
4. **End of term: SGB review.** Weekly reports, the risk report, and a decision on paid tiers and
   on an optional AI.

## 9. Next steps

1. Pilot at one school and measure real triage and response times.
2. Have first-language speakers review the isiZulu, Sesotho, Afrikaans and isiXhosa keywords.
3. Add SMS / WhatsApp replies through a gateway, and email through an HTTP email API.
4. Serve many schools from one installation (separate data per school), for district offices.
5. Replace the approximate calendar with the official DBE calendar each year.

## Sources

- Claude prices: [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) (checked 2026-10-28)
- Gemini prices and free-tier data use: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) (checked 2026-10-28)
- Render: [pricing](https://render.com/pricing) and [free tier](https://render.com/docs/free)
- Supabase: [pricing](https://supabase.com/pricing)
- Demo figures: [forecast_evaluation.md](forecast_evaluation.md), [classifier_evaluation.md](classifier_evaluation.md), [TECHNICAL.md](TECHNICAL.md)
