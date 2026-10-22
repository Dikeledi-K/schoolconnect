# Week 1: System Design & Ticket Classification Engine

**Curriculum outcome:** functional backend logic for request categorisation.

## What was built

| Area | Delivered |
|---|---|
| System design | `docs/ARCHITECTURE.md`: Mermaid diagram of the full 8-module target system, plus a diagram of the Week 1 classification flow |
| Taxonomy | `app/taxonomy.py`: the single source of truth for 7 categories (each with display name, description, routed staff role and keywords in 5 languages), 4 urgency levels, 6 language codes, 3 statuses, safety keywords |
| Classifier | `rules.py` (keyword scoring, language detection, urgency rules), `llm.py` (Claude / Gemini with strict JSON, validated against the taxonomy), `service.py` (LLM → rules fallback → safety guardrails) |
| Data layer | `Ticket` model with `SC-YYYYMMDD-XXXX` references and timestamps; `crud.py` for create, filter, status and stats |
| API | 9 endpoints, CORS, optional `X-API-Key` on endpoints that write data or return personal data |
| Data | 150 synthetic WhatsApp-style messages (36% non-English, 12 welfare cases); seed script spreading dates over 60 days |
| Evaluation | `scripts/evaluate_classifier.py` → `docs/classifier_evaluation.md` |
| Frontend | Streamlit: Overview, Send a message (with the 10111 / 112 safety notice), Staff inbox (filters, status changes, "why" explanation) |
| Quality | 96 pytest tests, GitHub Actions CI |

## Results

| Metric | Result | Target |
|---|---|---|
| Category accuracy (rules) | **96.0%** (dev 95.8%, holdout 96.7%) | ≥ 75% ✅ |
| Missed critical cases | **0 of 6** | 0 ✅ |
| High/critical recall | 83.3% | – |
| Exact urgency accuracy | 66.7% (mostly `low` predicted as `medium`) | – |
| Language accuracy | 97.3% | – |
| Tests | 96 passed | all pass ✅ |

## How it meets the curriculum outcome

"Functional backend logic for request categorisation" is met in four ways:

- Every message is categorised, given an urgency, language-detected and routed to a staff role by `classify_message()`.
- The classifier runs without an API key, so it works offline, in tests and in CI.
- It is measured against a labelled dataset with a reproducible evaluation script.
- It is exposed through a documented REST API (`/docs`) that the frontend uses.

## Grading rubric mapping

| Rubric area | Evidence |
|---|---|
| Problem understanding | README problem statement; categories mirror real SA school office work (admissions, fee exemptions, scholar transport, D6 portal) |
| System design | `docs/ARCHITECTURE.md` diagrams; component and endpoint tables; design decisions |
| Technical implementation | `app/` package with a clean split: taxonomy → classifier → crud → API |
| AI / ML use | Optional LLM with strict JSON schema, validation and fallback; rules baseline with confidence scores |
| Responsible AI | Safety guardrails (G1–G4), only message text sent to the LLM, prompt-injection tests, public reference lookup hides personal data |
| Testing & quality | 96 tests, CI on every push, evaluation targets enforced by a test |
| Evaluation | Accuracy, per-category precision/recall, confusion matrix, missed-critical count, dev/holdout split, honest caveats |
| Documentation | README, CLAUDE.md, ROADMAP, ARCHITECTURE, DATA, CHANGELOG, this report |
| UX | Parent page in plain language with an emergency notice; staff inbox puts critical tickets first |

## 5-minute demo script

1. **(0:00) The problem, 30 s.** "A school office gets hundreds of WhatsApp messages in five languages. A missing-child message can sit under fee questions for days."
2. **(0:30) The design, 45 s.** Open `docs/ARCHITECTURE.md` and show the 8-module diagram, then the Week 1 flow: rules or LLM, then guardrails.
3. **(1:15) The taxonomy, 30 s.** Open `app/taxonomy.py`: one file defines categories, staff roles and keywords in five languages.
4. **(1:45) Parent page, 1 min.** `streamlit run frontend/Home.py` → *Send a message*.
   - Type `Ke kopa ho ngodisa ngwanaka grade 8`. It shows Admissions, Sesotho, and a reference number.
   - Type `My son didnt come home from school today`. It shows a red **critical** banner with 10111 / 112.
5. **(2:45) Staff inbox, 1 min.** Critical tickets appear at the top. Filter by *Fees & Exemptions* and *isiZulu*. Open a ticket, expand "Why was it classified this way?", and change its status to *In progress*.
6. **(3:45) Evaluation, 45 s.** Run `python scripts/evaluate_classifier.py`: 96% accuracy and 0 missed critical. Show the confusion matrix and the honest caveats.
7. **(4:30) Safety and tests, 30 s.** Run `pytest`: 96 passed. Show `test_injection_cannot_lower_safety`: even if the LLM obeys "ignore all instructions", the guardrails still mark the message critical.

## Known limitations

- **The dataset is optimistic.** The same person wrote the dataset and the keywords, so expect lower accuracy on real messages. The next step is collecting anonymised real examples.
- **Non-English keywords need checking.** They need review by first-language speakers, and isiXhosa coverage is thin. isiZulu and isiXhosa stems overlap, so the two can be confused.
- **Urgency is coarse.** Information questions are often marked `medium` instead of `low`. This errs on the cautious side.
- **There are false positive safety flags.** Wellbeing words can raise urgency on non-welfare messages ("I am scared about the arrears"). This is by design (cautious) but adds staff work.
- **Endpoints have no individual staff accounts.** Protection is one shared API key; staff login arrives in Week 7.
- **There is no PII masking of message text yet.** Names inside the message text are sent to the LLM if a parent types them; Week 6 adds masking.
- **Tables are created with `create_all`, without migrations.** Schema changes in later weeks need a reset or a migration tool.
- **The LLM path is untested against the real APIs.** It is tested with mocks only, because there is no API key in this environment. The request was checked to be accepted by the Anthropic SDK.

## Retrospective questions for you

1. Which classifier mistakes in `docs/classifier_evaluation.md` would cause the most harm in a real school, and do you agree with how the guardrails trade false alarms for safety?
2. Could you explain to the panel, without notes, why isiZulu/isiXhosa keywords are matched as stems inside words but English keywords are not?
3. Who could you ask (classmates, family, a teacher) to review the isiZulu, Sesotho, Afrikaans and isiXhosa keywords and messages before Week 2?
