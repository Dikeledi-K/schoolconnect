# Sample data

## `data/sample_messages.csv`

150 **synthetic** parent messages written for this project. They are not real
messages and contain no real personal data: no surnames, phone numbers, ID
numbers or addresses. Place names (e.g. Soshanguve, Mamelodi) are real areas
and are used only for realism.

### Columns

| Column | Meaning |
|---|---|
| `id` | 1–150 |
| `message` | The parent's message, written in a WhatsApp style: typos, abbreviations ("pls", "hw", "gr 4"), missing apostrophes, code-switching |
| `expected_category` | The correct category (label written by hand) |
| `expected_urgency` | The correct urgency: `low` / `medium` / `high` / `critical` |
| `expected_language` | Main language: `en`, `zu`, `st`, `af`, `xh` |
| `learner_grade` | Optional grade (R, 1–12) |
| `split` | `dev` or `holdout`. Every 5th row is `holdout` |

### Mix

| Category | Messages |
|---|---|
| admissions | 30 |
| fees_exemptions | 28 |
| academic | 28 |
| transport | 18 |
| it_portal | 18 |
| other | 16 |
| learner_welfare | 12 (6 critical, 6 high) |

| Language | Messages |
|---|---|
| English | 96 (a few are code-switched, e.g. "Sawubona, can i pay … imali iyashoda") |
| isiZulu | 17 |
| Afrikaans | 16 |
| Sesotho | 14 |
| isiXhosa | 7 |

54 of 150 (36%) are mainly non-English.

### Deliberately hard cases

The set includes messages that mix topics, so the evaluation is not trivially easy:

- "apply for grade 10 … does the school offer maths and science" (admissions, but it mentions academic words)
- "Transport fees for the bus" (transport, but it mentions fees)
- "Is the portal down? … see marks" (IT, but it mentions marks)
- "my daughter missed the test because she was sick" (academic, but it mentions illness)
- "I am scared they will hand me over to lawyers" (fees, but it contains a wellbeing word)

### How labels were chosen

- **Category:** the staff member who should actually handle it.
- **Urgency:** `critical` = a child may be in danger now (abuse, missing,
  weapon, self-harm); `high` = same-day action (bullying, injury, deadlines
  today or tomorrow); `low` = simple information questions; otherwise `medium`.

### Honest limitations

- The same developer wrote the messages and the keyword rules, so accuracy on
  this set is **optimistic**. The `holdout` rows were never used to tune
  keywords. After the first evaluation run no keywords were changed, so dev and
  holdout scores are both "first run" numbers.
- The non-English messages and keywords were written by a non-first-language
  speaker. They need review by isiZulu, Sesotho, Afrikaans and isiXhosa speakers
  before real use. isiXhosa coverage is the thinnest.
- 150 messages is small: one message changes accuracy by about 0.7 points.

## Seeding the database

```bash
python scripts/seed_db.py --reset
```

Loads all 150 messages as tickets, classified by the current classifier, with
dates spread over the last 60 days. Weekdays and office hours (07:00–18:59) are
more likely, as in a real school office. A fixed random seed (42) gives the same
demo data every time. Older tickets are mostly resolved; a few old ones stay
`new` on purpose, for the SLA checks in Week 7.

## Week 5: synthetic ticket history (`scripts/generate_history.py`)

Forecasting needs much more history than 150 messages, so Week 5 adds a generator
(`app/synthetic.py`) that creates about **9,800 synthetic tickets over 24 months**, ending yesterday.

```bash
python scripts/generate_history.py --reset            # deletes ALL tickets, then generates (seed 42)
python scripts/generate_history.py --months 18 --seed 7
```

Use it **instead of** `seed_db.py` for forecasting demos (running both would double-count recent weeks).
No names or contact details are generated. Messages come from short templates (about 70% English,
the rest isiZulu, Afrikaans, Sesotho and isiXhosa), so they are less varied than `sample_messages.csv`;
the forecaster only uses each ticket's date and category.

### How the history is built

For each day and category an *expected* count is calculated, then the real count is drawn at
random around it (Poisson), so the data is noisy like the real world:

expected = base rate × calendar effects × weekday effect × growth

| Effect | Assumption |
|---|---|
| Base rates (mid-term Wednesday) | admissions 2, fees 3, academic 4, welfare 0.8, transport 1.5, portal 1.5, other 2 |
| Weekday | Mon 1.3, Tue 1.1, Wed 1.0, Thu 0.95, Fri 0.8, Sat 0.08, Sun 0.05 |
| School holidays | 15% of normal, except the week before term (80%) |
| Public holidays | 5% of normal |
| Growth | +10% per year |
| January opening | admissions ×5 (week before term + first 2 weeks); fees ×2.8 (first month); portal ×1.5 |
| Admissions window (Jul–Aug) | admissions ×4, portal ×1.6 |
| Placement offers (Oct–Nov) | admissions ×2.5 |
| Month start (days 1–7) | fees ×1.8 |
| Exams / reports issued | academic ×1.8 / ×3 |
| First 2 weeks of any term | transport ×3, welfare ×1.3 |
| One-off shocks (not in the calendar, so unpredictable) | portal crash 23 Jul 2025 (×8), transport strike 10 Mar 2025 (×6), app outage 12 May 2026 (×5) |

Response and resolution times get slower on busy days.

### The calendar is approximate

`config/school_calendar.yaml` holds best estimates of the typical South African public school
calendar for 2024–2027. **Verify against the official DBE calendar** (and the provincial admissions
calendar) before real use. A real school replaces it with its own dates and replaces the synthetic
history with real tickets; the forecasting code does not change.

