# Deploying SchoolConnect (Render + Supabase + GitHub Actions)

This guide is for a **first-time deployer**. Every value you paste is a secret: it goes into
your local `.env`, the Render dashboard or GitHub's secret settings. Never put it in a chat,
an email, an issue or a commit.

```
Parents & staff ──HTTPS──> schoolconnect-web (Render, Streamlit)
                                │  HTTPS + X-API-Key
                                ▼
                         schoolconnect-api (Render, FastAPI) ──TLS──> Supabase Postgres
                                ▲                                         ▲
GitHub Actions (scheduled) ─────┘ light calls (escalate, retention,       │
                                  keep-warm)                              │
GitHub Actions (scheduled) ───────────────────────────────────────────────┘
                                  heavy jobs run on GitHub (forecasts, weekly reports)
```

Everything here runs on **free tiers**. The trade-offs are listed in
[Free-tier limits](#free-tier-limits-checked-2026-10-28).

---

## 1. Accounts you need

| Account | What it runs | Sign up |
|---|---|---|
| GitHub | the code, CI tests, the scheduled jobs | you already have one: `Dikeledi-K/schoolconnect` (public) |
| Supabase | the Postgres database | https://supabase.com, "Continue with GitHub" |
| Render | the two web services | https://render.com, "GitHub" sign-in |

## 2. Supabase: the database

1. On Supabase, click **New project**:
   - **Name:** `schoolconnect`
   - **Password:** use **Generate a password**, and keep it in a password manager.
   - **Region:** **Central EU (Frankfurt)**.
2. When the project is ready, click **Connect**, then **Connection string**, then **Type: URI**,
   then **Transaction pooler** (port **6543**).
3. Copy the string and replace `[YOUR-PASSWORD]` with the database password.

**Why the transaction pooler?**
- **No IPv6 on Render.** Render has no IPv6, and Supabase's direct connection is IPv6-only. The
  shared pooler works over IPv4.
- **Render recommends it.** Render's guide recommends the transaction mode for web services.
- **It needs one driver setting.** Transaction mode cannot keep prepared statements, so
  `app/db.py` turns them off automatically when the port is 6543 (`prepare_threshold=None`).
  It also uses a small pool of 3 connections, checked before use and replaced every 5 minutes.

Keep the string in your local `.env` as **`SUPABASE_DATABASE_URL=...`**. The app never reads
that name, so your laptop keeps using the local SQLite database.

## 3. Production secrets

Generate one long random value for each secret. In this project they are already in your local
`.env` as `PROD_API_KEY`, `PROD_JOBS_TOKEN` and `PROD_INBOUND_SECRET`. To make a new one yourself:
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.

| Secret | Where it goes | Used for |
|---|---|---|
| `DATABASE_URL` | Render (API), GitHub | the Supabase transaction-pooler string |
| `API_KEY` | Render (API **and** web, the same value) | the web app proves it is the school's own frontend |
| `JOBS_TOKEN` | Render (API), GitHub | scheduled jobs, and signing stored forecasts |
| `INBOUND_SECRET` | Render (API) | the signed email/WhatsApp webhook (`docs/INTEGRATIONS.md`) |

With `ENVIRONMENT=production` (set in `render.yaml`), the API **refuses to start** if `API_KEY`
or `JOBS_TOKEN` is empty, if password hashing is weaker than 600 000 iterations, or if
`DATABASE_URL` is still SQLite.

## 4. Load the demo data into Supabase (from your laptop)

> ⚠️ **`generate_history.py --reset` deletes EVERY table**: all tickets, staff accounts,
> replies, reports, events and the outbox. Run it only on an empty project, or when you really
> want to start again.

In PowerShell, in the project folder, with the virtual environment active:

```powershell
# Point THIS terminal at Supabase (only this window; .env keeps saying SQLite).
$env:DATABASE_URL = (Select-String '^SUPABASE_DATABASE_URL=' .env).Line.Split('=',2)[1]
# Stored forecasts are signed with the PRODUCTION jobs token, so the live API can trust them.
$env:JOBS_TOKEN = (Select-String '^PROD_JOBS_TOKEN=' .env).Line.Split('=',2)[1]
# The demo scripts read the staff password from this variable (never typed on the command line).
$env:DEMO_STAFF_PASSWORD = (Select-String '^DEMO_STAFF_PASSWORD=' .env).Line.Split('=',2)[1]

python scripts/generate_history.py --reset   # ~24 months of synthetic history (deletes everything first!)
python scripts/demo_week6.py                 # privacy, corrections, replies (password: DEMO_STAFF_PASSWORD)
python scripts/demo_week7.py                 # staff, webhook, fee exemption, escalation
python scripts/make_weekly_reports.py --weeks 4
python scripts/evaluate_forecast.py          # also checks the January numbers
python scripts/refresh_forecasts.py          # store today's + the pinned demo forecast

# Back to SQLite: close this terminal, or
Remove-Item Env:DATABASE_URL, Env:JOBS_TOKEN, Env:DEMO_STAFF_PASSWORD
```

The demo scripts take the staff password from the `DEMO_STAFF_PASSWORD` environment variable set above
(or `--password`).
They print the demo logins: `principal@ubuntu-demo.school.example`, `deputy@…`, `admin@…`,
`finance@…`, `teacher@…` and `it@…`.

**Manual Postgres check.** The first run of the commands above is also the first real test of
`init_db()` and `migrate()` on Postgres. They must finish without errors, and
`python -c "from app.db import migrate; print(migrate())"` (with `DATABASE_URL` still set) must
print `[]`, which means nothing is left to add.

## 5. Render: the two services (Blueprint)

1. Sign in at https://dashboard.render.com with GitHub. Allow Render to see the `schoolconnect`
   repository.
2. Click **New +**, then **Blueprint**, and choose the `schoolconnect` repository. Render reads
   `render.yaml` and shows **schoolconnect-api** and **schoolconnect-web** (Free, Frankfurt).
3. Render asks for every `sync: false` value. Paste:

   | Service | Key | Value |
   |---|---|---|
   | api | `DATABASE_URL` | your `SUPABASE_DATABASE_URL` value |
   | api | `API_KEY` | `PROD_API_KEY` |
   | api | `JOBS_TOKEN` | `PROD_JOBS_TOKEN` |
   | api | `INBOUND_SECRET` | `PROD_INBOUND_SECRET` |
   | api | `CORS_ORIGINS` | `https://schoolconnect-web.onrender.com` |
   | api | `ANTHROPIC_API_KEY` | leave empty (the AI is off: `LLM_PROVIDER=rules`) |
   | web | `API_BASE_URL` | `https://schoolconnect-api.onrender.com` |
   | web | `API_KEY` | `PROD_API_KEY` (the same as on the API) |

4. Click **Apply**. The first build takes a few minutes.
5. Open each service and check its URL at the top of the page. If Render added a suffix (for
   example `schoolconnect-api-x1y2.onrender.com`), update `API_BASE_URL` on the web service and
   `CORS_ORIGINS` on the API under **Environment**, then **Save, rebuild and deploy**.

Every push to `main` redeploys both services (`autoDeployTrigger: commit`). The Python version
comes from `.python-version` (3.11), the same as CI.

## 6. GitHub: secrets for the scheduled jobs

On GitHub, open the repository, then **Settings**, **Secrets and variables**, **Actions**, and
**New repository secret**. Add these four:

| Name | Value |
|---|---|
| `API_BASE_URL` | the API URL, e.g. `https://schoolconnect-api.onrender.com` (no trailing `/`) |
| `WEB_URL` | the web URL, e.g. `https://schoolconnect-web.onrender.com` |
| `JOBS_TOKEN` | `PROD_JOBS_TOKEN` |
| `DATABASE_URL` | your `SUPABASE_DATABASE_URL` value |

Then go to **Actions**, open **Scheduled jobs**, click **Run workflow**, and run each job once to
check it.

### Why GitHub also needs `DATABASE_URL` (the trade-off)

The forecasts and weekly reports are **heavy**: on Render's 0.1 CPU they take about 2 minutes
each (`docs/TECHNICAL.md`). So they run **on GitHub's runner** (a full virtual machine), connected
straight to Supabase, and store their results there. The API only reads them, in milliseconds.

- **Benefit:** the live site is never slowed down by a long calculation, and the January demo
  view reads a stored forecast.
- **Cost:** one more place holds the database password. GitHub encrypts secrets, never shows
  them again, and masks them in logs. Still, anyone who can change `.github/workflows/` on `main`
  could misuse it. Keep the repository's write access to yourself, and rotate the password if
  that changes (section 10).

Escalation, retention and keep-warm stay as **calls to the Render API**, because they are quick
and belong to the app's own logic and audit trail.

## 7. Scheduled jobs and free instance hours

GitHub's clock is UTC; South Africa is UTC+2. Times avoid the start of the hour, because GitHub
says scheduled runs are most often delayed then.

| Job | When (SAST) | Runs where | What it does |
|---|---|---|---|
| escalate | Mon–Fri every 15 min, 06:07–17:07 | Render API (`POST /jobs/escalate`) | overdue tickets one level up; 30-min critical alerts |
| keep-warm | Mon–Fri every 14 min, 07:03–16:13 | Render API `/health` + web `/` | stops the services sleeping during school hours |
| forecasts | every day 05:23 | GitHub → Supabase | stores today's forecast and the pinned demo date (2025-12-15) |
| weekly-reports | Mondays 06:13 | GitHub → Supabase | makes last week's 6 reports |
| retention (dry run) | Sundays 02:17 | Render API (`POST /jobs/retention?dry_run=true`) | reports what *would* be anonymised; changes nothing |

Every call:
- waits up to 180 s, because a sleeping service takes about a minute to wake;
- retries once after 20 s;
- **turns the GitHub run red** on any non-2xx answer, so you get an email.

**Free instance hours.** A service uses hours only while it is awake, and it falls asleep
15 minutes after its last request. One workspace has 750 hours a month for all its services.
This assumes 23 weekdays, the most in any month:

| Service | Awake | Hours / month |
|---|---|---:|
| schoolconnect-api | 06:07 to about 17:22 on weekdays (escalation every 15 min) | 11.25 h × 23 = **259** |
| schoolconnect-web | 07:03 to about 16:28 on weekdays (keep-warm every 14 min) | 9.4 h × 23 = **216** |
| schoolconnect-api | Sunday retention wake-up (about 20 min) × 5 | **2** |
| | **Total from the schedule** | **≈ 477 of 750** |

That leaves about **270 hours** for evenings, weekends, rehearsals and the panel. A demo session
with both services awake for an hour uses about 2 hours. Forecasts and reports run on GitHub, so
they use no Render hours. GitHub Actions is free for public repositories.

**Real anonymisation.** The retention job stays a **dry run**. Change it to `dry_run=false` in
`.github/workflows/jobs.yml` only after the principal (as Information Officer) approves, and
record it here:

> Principal's approval for real retention runs: **not given** (dry run only). Date: ____ Name: ____

## 8. Smoke test the live site

```powershell
python scripts/smoke_test_prod.py --api https://schoolconnect-api.onrender.com `
    --web https://schoolconnect-web.onrender.com --email principal@ubuntu-demo.school.example
```

It reads the password from `DEMO_STAFF_PASSWORD` and the API key from `PROD_API_KEY` in `.env`,
or asks for them at a hidden prompt. It prints PASS/FAIL with timings for:
- health (including the wake-up);
- login;
- creating a ticket with the API key;
- My work;
- the analytics summary;
- the January forecast;
- the latest weekly report PDF;
- "a learner-welfare ticket is hidden from a class teacher (404)";
- the web home page.

It exits with an error if anything fails. It creates one ticket labelled "Smoke test - please
ignore".

## 9. Before a presentation

1. **Open both URLs 5 minutes early**: the web home page and `<API>/health`. A sleeping free
   service takes about a minute to wake, and the first page after waking is slower.
2. Log in as the principal and open **Forecast and workload → Backtest demo** once, which warms
   the cache.
3. Have the backup ready (`docs/PRESENTATION.md`): the local run, the screenshots in
   `docs/screenshots/` and the recorded GIF.
4. During school hours on weekdays the keep-warm job keeps both services awake anyway.

## 10. Rotating secrets

Rotate a secret whenever it might have leaked, when someone leaves, and once a term.

| Secret | How |
|---|---|
| `API_KEY` | new value, then Render **Environment** on **both** services (the same value), then redeploy |
| `JOBS_TOKEN` | new value on Render (API) **and** GitHub, then run **forecasts** by hand (stored forecasts signed with the old token are ignored until they are re-made) |
| `INBOUND_SECRET` | new value on Render, then give it to the gateway's owner |
| Supabase password | Supabase → **Project Settings** → **Database** → **Reset database password**, then update `DATABASE_URL` on Render, GitHub and your `.env` |
| A staff password | the person logs in and the admin re-creates the account with `scripts/create_staff.py`, or deactivates it |

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| The first page takes about a minute, or shows Render's loading page | the free service was asleep | normal; open the URLs early (section 9) |
| API deploy fails: `Refusing to start with ENVIRONMENT=production: API_KEY is empty` | a secret was not pasted | Render → schoolconnect-api → Environment → add it |
| API logs: `connection refused`, `Network is unreachable`, IPv6 address | the **direct** Supabase URL was used | use the **Transaction pooler** string (port 6543) |
| `password authentication failed` | wrong password, or `[YOUR-PASSWORD]` still in the URL; special characters need %-encoding | copy the string again from Supabase **Connect** |
| `prepared statement "…" already exists` | transaction pooler without the setting | make sure the URL's port is **6543** (`app/db.py` then turns prepared statements off) |
| Web app says "The API rejected the request" / every call answers 401 | `API_KEY` differs between web and API, or the login expired | set the same `API_KEY` on both; log in again |
| Staff pages log you out on refresh | Streamlit keeps the login per browser session | use the sidebar links, not the browser's refresh |
| GitHub job red: `HTTP 401` | `JOBS_TOKEN` differs between GitHub and Render | set the same value on both |
| GitHub job red: timeout | Render was waking up, or deploying | it retries once; run it again by hand |
| Forecast pages slow (about 2 min) | no stored forecast for that date, or it was signed with another token | run **forecasts** by hand (Actions → Scheduled jobs → Run workflow) |
| Render: "exceeded memory" / restarts | above 512 MB | measured peak is about 250 MB (`docs/TECHNICAL.md`); check for an unusual request in the logs |
| Supabase project "paused" | 7 days without any database activity | Supabase → **Restore project**; the daily forecast job normally prevents this |
| Scheduled jobs stopped running | GitHub switches schedules off after 60 days without a commit | Actions → Scheduled jobs → **Enable workflow** |
| Services suspended near month-end | 750 free instance hours used up | check Render → Billing → usage; reduce keep-warm or wait for the 1st |

## Free-tier limits (checked 2026-10-28)

**Render, free web services:**
- 512 MB RAM and 0.1 CPU;
- they sleep after 15 minutes without traffic and take about a minute to wake;
- 750 instance hours per workspace per month;
- the file system is wiped on restart, redeploy and sleep;
- outbound ports 25, 465 and 587 are blocked.

  **So the free API cannot send real email over SMTP**, and `NOTIFY_MODE` stays `dry_run`. Real
  email needs a paid instance, or an HTTP email API (backlog).
- They cannot receive private-network traffic.

**Supabase, free plan:**
- 500 MB database and 2 active projects;
- projects pause after one week of inactivity;
- no backups.

**GitHub Actions:**
- free for public repositories on standard runners;
- scheduled runs can be delayed at busy times, especially on the hour;
- scheduled runs switch off after 60 days without repository activity.

## Sources

- Render: [Deploy for free](https://render.com/docs/free)
- Render: [Blueprint YAML reference](https://render.com/docs/blueprint-spec)
- Render: [Setting your Python version](https://render.com/docs/python-version)
- Render: [Connect a Render service to Supabase Postgres](https://render.com/articles/how-to-connect-a-render-service-to-supabase-postgres)
- Render: [Pricing](https://render.com/pricing) (free and Starter instances)
- Render community: [Issues connecting Render to Supabase after the IPv6 transition](https://community.render.com/t/issues-connecting-render-to-supabase-after-ipv6-transition/24156)
- Supabase: [Connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres) (direct vs pooler, prepared statements)
- Supabase: [Pricing](https://supabase.com/pricing)
- GitHub: [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- GitHub: [Events that trigger workflows: schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
