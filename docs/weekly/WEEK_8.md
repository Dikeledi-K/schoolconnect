# Week 8 – Deployment, Optimisation & Industry Showcase

**Sprint goal:** finalise and deploy.
**Deliverables:**
- the deployed AI Business Operations Platform;
- technical documentation;
- a business case;
- a portfolio;
- a panel presentation.

## What was built

1. **Deployment as code.**
   - `render.yaml` defines two free Render web services in Frankfurt: `schoolconnect-api` (FastAPI)
     and `schoolconnect-web` (Streamlit, run from the repo root so the theme loads).
   - Both auto-deploy on every push to `main`.
   - Secrets are `sync: false`, so they are typed into Render and never stored in git (a test checks
     this).
   - Python 3.11 is pinned in `.python-version` for Render *and* CI.
   - Requirements are split into runtime and dev/test.
2. **Supabase-ready database engine.**
   - psycopg 3 over the **transaction pooler** (port 6543). Render has no IPv6, and Supabase's direct
     connection is IPv6-only.
   - Prepared statements are turned off for that mode.
   - A small pool (3 + 2) with `pool_pre_ping`, `pool_recycle=300` and `sslmode=require`.
   - SQLite behaviour is unchanged.
3. **Production safety.** With `ENVIRONMENT=production` the API refuses to start in any of these
   cases:
   - `API_KEY` or `JOBS_TOKEN` is empty;
   - password hashing is below 600 000 iterations;
   - the database is SQLite.

   A **"Demo: fictional school, synthetic data"** banner appears on every page and in the API docs.
4. **Stored forecasts.**
   - Every night, GitHub computes today's forecast and the **pinned demo date** (15 Dec 2025, the
     January backtest), signs it with an HMAC and stores it in Supabase.
   - The forecast endpoints read the stored result first. It is used only for exactly the same data
     (a fingerprint) and the same library versions.
   - Tests prove the answers are identical to computing live, and that tampered or unsigned rows are
     never unpickled.
5. **Scheduled jobs on GitHub Actions**, all off the hour, because GitHub delays runs most at the
   start of the hour:
   - **Calls to Render:** escalation every 15 minutes (06:00–17:00 SAST), keep-warm every 14 minutes
     (07:00–16:00), and a weekly retention **dry run**.
   - **Run on GitHub against Supabase:** forecasts (daily) and weekly reports (Mondays).
   - Every call waits up to 180 s for a sleeping service, retries once, and turns the run red on
     failure.
   - Estimated use: **≈ 477 of 750** free instance hours a month.
6. **Smoke test.** `scripts/smoke_test_prod.py` makes 9 checks with timings, takes passwords from a
   hidden prompt or `.env`, and exits non-zero on any failure.
7. **Optimisation, measured first** (`scripts/measure_performance.py`, with the CPU capped at
   0.1 core to simulate Render):
   - **Peak memory:** 250 MB of 512 MB.
   - **Stored forecasts:** the backtest view takes **7.7 s** instead of **151 s**.
   - **Workload maths:** a dict instead of 2,700 pandas lookups makes it **30–60× faster**, with
     identical results.
   - **Start-up:** scikit-learn loads only when needed, so the API starts in **21.5 s instead of 39 s**
     at 0.1 CPU.
   - **Risk page:** the classifier check is cached and the PDF is built on request.
   - **Frontend:** spinners, and no duplicate API calls.
   - **Indexes:** none added (every query ≤ 6 ms).
8. **Both evaluations re-run.**
   - The January backtest is unchanged: forecast **421** vs **486** (16% error), **84%** of days
     inside the range, admin clerk **86%** vs **88%**.
   - The classifier is still at **96.0%** with 0 missed critical cases.
9. **Documentation:**
   - [TECHNICAL.md](../TECHNICAL.md)
   - [USER_GUIDE.md](../USER_GUIDE.md), with 10 screenshots made by `scripts/take_screenshots.py`
   - [DEPLOYMENT.md](../DEPLOYMENT.md), for a first-time deployer, with sources
   - [BUSINESS_CASE.md](../BUSINESS_CASE.md)
   - [PRESENTATION.md](../PRESENTATION.md)
   - the portfolio [README](../../README.md)

   Every Vercel mention was replaced.
10. **Fixes found along the way:**
    - the parent reference lookup now ignores a copied full stop;
    - the sidebar now covers all 9 pages (the selected "Forecast" label was white on white);
    - `evaluate_forecast.py` now writes UTF-8 on Windows.
11. **Tests:** 402 passing (31 files), up from 361.

## Curriculum mapping

| Curriculum item | Where |
|---|---|
| Deploy the AI Business Operations Platform | `render.yaml`, `app/db.py`, `.github/workflows/jobs.yml`, `docs/DEPLOYMENT.md` |
| Optimise performance and reliability | measurements in `docs/TECHNICAL.md` §8; stored forecasts; the workload speed-up; production checks; smoke test |
| Technical documentation | `docs/TECHNICAL.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` |
| Business case presentation | `docs/BUSINESS_CASE.md`, `docs/PRESENTATION.md` |
| Professional portfolio | `README.md`, `docs/screenshots/`, `docs/USER_GUIDE.md` |
| Presentation to a mock executive / industry panel | the 10 slides, live demo script, backup plan and 12 Q&A in `docs/PRESENTATION.md` |

## Grading rubric mapping

**Technical skills (40%): portfolio completeness**

| Evidence |
|---|
| One repository deploys both services from a Blueprint; secrets never in git (tested) |
| 402 automated tests: every week's module, plus deployment config, production checks, stored forecasts, jobs and the smoke test |
| Measured, not guessed: memory and timings at a simulated 0.1 CPU, and every optimisation justified by a number |
| Reproducible evaluations: the January backtest and classifier figures unchanged after optimisation |
| Smoke test of the full flow (login, ticket, my work, analytics, forecast, PDF, welfare privacy, web) |

**Professional skills (60%): communication, branding, presentation**

| Evidence |
|---|
| A consistent "warm & friendly" brand, the "Every parent heard, every child safe" line, and a demo banner on every page |
| A plain-language user guide for parents, staff and the principal/SGB, with screenshots |
| A business case with every assumption labelled, and costs from current, cited pricing |
| A panel talk with speaker notes, a timed live demo, a backup plan and 12 prepared answers |
| A deployment guide a first-time deployer can follow, with troubleshooting |

## 5-minute demo script

Follow "Live demo: one parent message, end to end" in [PRESENTATION.md](../PRESENTATION.md). In
short:

1. **(30 s)** Open the live site, opened 5 minutes early. Point at the demo banner.
2. **(60 s)** As a parent on a phone-sized window, send an admissions question and copy the
   reference.
3. **(60 s)** As the admin clerk: the ticket is already in **My work**. Draft a reply from school
   facts, then **Approve and send** ("queued, dry run").
4. **(45 s)** Send "my son did not come home". It is critical and at once in the **deputy's** My
   work, and invisible to the clerk.
5. **(45 s)** As the principal: **Forecast → Backtest demo**, read from the stored result in seconds
   (421 vs 486, and the admin clerk's 86% week). Then **Risk**: 23/23 injection checks.
6. **(30 s)** Close on cost (about R700 a month for a real school) and the pilot ask.

## Smoke test output

**Local run** (2026-10-29, API on http://localhost:8000, web on http://localhost:8501, demo
database):

```
Smoke test of http://localhost:8000 and http://localhost:8501

PASS     2.1 s  API /health (wake-up)  (status ok, AI mode rules (first call includes wake-up))
PASS     0.6 s  staff login  (logged in as Mrs N. Dlamini (principal))
PASS     0.0 s  create a ticket with the API key  (SC-20261029-0002 (academic))
PASS     0.0 s  /workflow/my-work  (0 open ticket(s))
PASS     0.1 s  /analytics/summary  (118 messages last week (135 the week before))
PASS     0.4 s  /forecast?as_of=2025-12-15 (January backtest)  (45 days, 507 expected, 0.4 s)
PASS     0.0 s  download the latest weekly report PDF  (report #20, 5 KB)
PASS     0.6 s  learner-welfare ticket hidden from a class teacher  (ticket #9887: principal 200, class teacher 404)
PASS     0.0 s  web home page loads  (home page and /_stcore/health answer 200)

9/9 checks passed in 3.9 s
```

**Live run** (Render + Supabase): *to be added after the deployment steps in
[DEPLOYMENT.md](../DEPLOYMENT.md) are completed.*

## Known limitations

- **The live site isn't up yet.** The Render and Supabase accounts have to be set up by the owner,
  so the live smoke test is pending.
- **The free tier sleeps.** Waking takes about a minute plus about 20 s of start-up at 0.1 CPU.
  Keep-warm covers weekday school hours only.
- **No real email.** Render's free tier blocks SMTP ports, so notifications stay in the outbox (dry
  run).
- **Slow uncached pages.** A forecast for a date that is not stored takes about 2.5 minutes on
  Render. Pages that compute live (risk, analytics) take a few seconds.
- **Free Supabase:** no backups, and it pauses after 7 days without activity.
- **GitHub schedules** can run late, and stop after 60 days without a commit.
- **Assumed impact.** The business-case savings rest on labelled assumptions; only a pilot can
  measure them.
- **Not yet tested on Postgres here.** `migrate()` was tested on SQLite only (no Docker on the dev
  machine). The manual Postgres check is the first demo load into Supabase (DEPLOYMENT.md §4).

## Retrospective questions

1. The free tier made performance visible: a forecast that took 12 s on a laptop took 151 s at
   0.1 CPU. Which other design decisions would change if this ran on the cheapest paid tier
   instead?
2. Where is the line between "keep the demo fast" (stored, pre-computed results, keep-warm) and
   "show the system honestly"? How would you explain the stored forecast to a sceptical panel
   member?
3. Which of the labelled business-case assumptions (3 minutes of triage per message, 30% saved on
   replies, half the follow-ups avoided) is the most likely to be wrong, and how would a one-month
   pilot measure it?
