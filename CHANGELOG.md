# Changelog

All notable changes, one section per bootcamp week.

## [week-1] 2026-10-22: System Design & Ticket Classification Engine

### Added
- Project setup: `CLAUDE.md`, `docs/ROADMAP.md`, `.gitignore`, `requirements.txt`,
  `.env.example`, `pytest.ini`, GitHub Actions CI (pytest on Python 3.11).
- `app/taxonomy.py`: 7 categories with routed staff roles and keywords in
  English, isiZulu, Sesotho, Afrikaans and isiXhosa; urgency levels; languages;
  statuses; safety keywords.
- Classifier (`app/classifier/`): offline rules, optional Claude/Gemini with
  strict JSON and validation, rules fallback, and child-safety guardrails that
  only raise urgency.
- Database (`Ticket` model, SQLite locally) with `SC-YYYYMMDD-XXXX` references.
- API: `/health`, `/taxonomy`, `/classify`, `/tickets` (create, list with
  filters, get, by reference, status update), `/stats`; CORS; optional `X-API-Key`.
- 150 synthetic sample messages (`data/sample_messages.csv`, `docs/DATA.md`) and
  `scripts/seed_db.py` (dates spread over 60 days).
- `scripts/evaluate_classifier.py` → `docs/classifier_evaluation.md`
  (96.0% accuracy, 0 missed critical cases).
- Streamlit frontend: Overview, Send a message, Staff inbox.
- 96 tests: taxonomy, rules, guardrails, mocked LLM, prompt injection, API, data and targets.
- `docs/ARCHITECTURE.md` with Mermaid diagrams.
