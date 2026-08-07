# AI Intake Phase A Acceptance

Evidence-based acceptance record for AI Intake Phase A. All findings are from
executed tests, not claims. No live DeepSeek API was called; deterministic
local mocks were used.

## Gates

| Gate | Evidence |
| --- | --- |
| Receptionist authority boundary documented and enforced | `docs/adr/0002-*`; state machine; completeness engine; emergency screening |
| Deterministic completeness service | `apps/ai_intake/services/completeness.py`; completeness tests |
| AI cannot independently complete/submit | backend gate overrides `propose_review`; submission requires `confirmed` |
| Patient review/correction/confirmation | review/correction/confirm/submit endpoints; tests |
| Duplicate patient-turn issue resolved | provider-history regression test (each answer/assistant appears exactly once) |
| DeepSeek errors safely redacted | provider failure matrix; generic localized patient messages |
| Prompt injection tests pass | injection corpus tests (system prompt, role override, forced completion, etc.) |
| Semantic validation rejects unsupported output | Pydantic + semantic validation tests |
| Extracted facts retain evidence/provenance | evidence ids + grounding guard + draft provenance tests |
| Hallucinated facts excluded | grounding guard tests (fabricated medication/allergy/duration rejected) |
| Emergency deterministic, not downgradable | emergency authority tests |
| Retries and token/history limits bounded | retry policy + history budget tests and settings |
| AI content does not populate doctor-authored fields | draft separation tests |
| Patient/doctor projections safe | patient review hides provider data; doctor view shows provenance |
| EN/AR/CKB | i18n keys present in all locales; Arabic/Kurdish emergency matchers |
| Backend tests pass | full suite + Phase A suites |
| Frontend tests pass | vitest suite |
| Playwright | documented for Phase A (see deferred notes) |
| PostgreSQL concurrency | real-Postgres concurrency suite |
| Docker | backend/frontend images build and start |
| Git pushes succeed | commits pushed to `main` |

## Evaluation limitations (documented)

- The emergency matcher is a keyword rule set, not a clinician-reviewed rule
  engine. No emergency-detection certification is claimed.
- No diagnostic accuracy, treatment accuracy, medical safety certification, or
  clinician equivalence is claimed.
- Model quality metrics measure technical properties (JSON validity, schema
  validity, grounding, etc.), not medical correctness.
- Clinician review is required before any intake-derived information is treated
  as clinically valid.

## Deferred to AI Intake Phase B

- Playwright end-to-end browser flows (documented in the phase plan but not
  executed in this phase).
- Real provider smoke test (requires explicit, approved integration config and
  synthetic non-medical content only).
- Clinician-reviewed emergency rule sets.
- Live-model quality evaluation on the synthetic evaluation set.
- Railway deployment verification after push (read-only).

## Docs and ADRs

- `docs/AI_INTAKE_ARCHITECTURE.md`
- `docs/AI_RECEPTIONIST_SCOPE.md`
- `docs/AI_INTAKE_INFORMATION_SCHEMA.md`
- `docs/AI_INTAKE_COMPLETENESS.md`
- `docs/AI_INTAKE_PATIENT_CONFIRMATION.md`
- `docs/AI_INTAKE_EMERGENCY_SAFETY.md`
- `docs/AI_INTAKE_PROMPT_SECURITY.md`
- `docs/AI_INTAKE_PROVIDER_FAILURES.md`
- `docs/AI_INTAKE_DATA_PROVENANCE.md`
- `docs/AI_INTAKE_PERMISSION_MATRIX.md`
- `docs/AI_INTAKE_PHASE_A_SECURITY.md`
- `docs/AI_INTAKE_PHASE_A_ACCEPTANCE.md`
- `docs/adr/0002-ai-receptionist-authority-boundary.md`
- `docs/adr/0003-ai-intake-patient-confirmation.md`
- `docs/adr/0004-ai-intake-provenance-and-draft-generation.md`
