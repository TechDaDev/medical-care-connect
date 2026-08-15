# AI Intake Phase D Acceptance

Status date: 2026-08-15

## Outcome

Software implementation and live evaluation are complete. Final repository, regression, container, deployment, and cleanup evidence is recorded below during release verification. Clinical review remains independently unreviewed.

## Delivered

- 100-case synthetic `mcc-ai-intake-eval-v3`: 50 development / 25 validation / 25 final; EN 30 / AR 20 / ar-IQ 20 / CKB 20 / mixed 10.
- Final split explicitly blinded, non-tuning, and separately gated.
- Language-aware evidence normalization and field-scoped canonical aliases without global grounding relaxation.
- Evaluator scoring for per-language grounding/semantic/question metrics, clarification, repetition, hallucination, injection, premature completion, emergency bypass, tokens, and latency.
- Deterministic completeness integration and emergency pre-provider bypass.
- Review worksheet context, strict metadata-only import, reviewer-role requirement, and truthful zero-approved fixture layer.
- Prompt decision: `KEEP mcc-intake-v2`.
- Model decision: `KEEP CURRENT MODEL` (`deepseek-v4-flash`).
- Ruleset decision: keep `mcc-emergency-rules-v1`.

## Live evidence

Initial v3 prompt-v2 baseline: 25/25 completed, 20 calls, 5 bypasses, 0 failures; JSON/schema/language 100%; semantic 60%; grounding 62.5%; question selection 75%; repeats 0%; hard containment passed. Dataset composition was then corrected before final exposure.

Frozen validation: three complete 25-case runs, 60 successful provider calls, 15 emergency bypasses, 0 provider failures. JSON/schema/language 100% all runs; semantic 65/70/70%; grounding 57.14% all; question selection 100/100/80%; repeats 0%; unsupported/hallucinated acceptances 0; injection, premature completion, and emergency containment 100%.

Final blinded: one complete 25-case run, 20 successful calls, 5 bypasses, 0 failures. JSON/schema/language 100%; semantic 65%; grounding 57.14%; question and clarification 100%; repeats 0%; hard safety containment 100%.

## Clinical evidence

56/56 exported and import-validated. Reviewed EN 0/37, AR 0/11, CKB 0/8. Dispositions: unreviewed 56; all others 0. No qualified reviewer was available/evidenced.

## Release gates

- Backend: Django checks/migrations clean; 611 tests run, 589 passed, 0 failed, 22 skipped. AI Intake Phase C+D targeted regression 43/43 passed.
- PostgreSQL: 8/8 real row-locking concurrency tests passed, covering duplicate/different answers, retry, confirm, submit/draft/notification dedupe, cancellation race, and emergency race.
- Dependencies: `pip check` and `pip-audit` clean; no known runtime vulnerabilities. Frontend production dependency audit clean; full npm development audit retains three high-severity dev-only findings.
- Frontend: ESLint and TypeScript clean; Vitest 180/180; coverage 180/180; production build clean.
- Playwright: 194 passed, 0 failed, 2 intentional desktop/mobile project skips. Deterministic mock provider only; accessibility, keyboard, RTL, mobile, patient, doctor, emergency, injection, draft, and permission paths passed.
- Docker: no-cache backend `sha256:8dccab407e16fba9dddef7b0ca4d901c21a8798ef9bde440d6e784edc3678f87`; frontend `sha256:61a20b313dce5df6a295476a571af179a3b5cd5547533cfa93fc85d718ea9171`. Backend runs non-root, production deploy check and pip check pass, live evaluation defaults off without provider key, isolated migrations pass, health/readiness return 200.
- Codebase graph refreshed: backend 4,142 nodes / 18,607 edges; frontend 7,017 nodes / 9,651 edges. Evaluation, grounding, review, provider, and dynamic test/command paths classified.
- Cleanup: temporary reports/CSV/logs, browser artifacts, test database, smoke containers/network, and run-scoped synthetic DB/storage objects are zero.
- Protected `docs/project-skills.md`: untouched, untracked, unstaged, uncommitted; SHA-256 `01b5f48d80f1b577b938142fd206706e78c2af87a24caf0d6eb2230e0f3010a4`.
- Git push and automatic Railway deployment remain final external gates for this pre-release snapshot.

`SOFTWARE PHASE D: PARTIAL`

`EMERGENCY CLINICAL REVIEW: UNREVIEWED`
