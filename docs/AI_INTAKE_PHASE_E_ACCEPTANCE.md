# AI Intake Phase E Acceptance

Status date: 2026-08-15

## 1. Executive summary

Phase E software is PARTIAL. Deterministic safety, implementation, regression, and release gates passed; one-shot final quality did not. Emergency clinical review remains UNREVIEWED.

## 2. Software Phase E status

`PARTIAL`: final question selection 80% is below 95%; final Iraqi grounding is 50%; final CKB grounding is 0%.

## 3. Emergency clinical-review status

`UNREVIEWED`: no real qualified reviewer evidence supplied.

## 4. Skills used

`caveman`, `memu-retrieve`, `acceptance-orchestrator`, `mcc-phase-acceptance`, `mcc-medical-privacy-security`, `mcc-i18n-en-ar-ckb`, and `advanced-evaluation`.

## 5. Baseline commits

Backend `348b7c5b9931ef28c155d8cb1190833e4049bdfe`; frontend `b502e8ca751a4b65c1d4f12502f7bf9f61db5dfe`. Both matched origin at start.

## 6. Codebase-memory pre-change findings

Grounding used NFKC/basic Arabic variants plus substring aliases, without bound original spans and with incomplete unsafe-context guards. Review import lacked qualification/language competence. Evaluator lacked v4/per-language unsafe-acceptance reporting.

## 7. Codebase-memory post-change findings

Indexes refreshed: backend 4,357 nodes / 19,091 edges; frontend 7,018 nodes / 9,656 edges. Traces prove evaluator/semantic validator → `grounding_evidence` → bounded phrase/unsafe-context/canonical-span helpers, and management command/tests → strict review import. Zero-degree results were documentation, test classes, dynamic registry files, and expected naming gaps—not orphaned runtime paths.

## 8. Clinical-review execution

Export/import exercised with all 56 rows. Import remains metadata-only and rejects executable-field mutation.

## 9. Qualified reviewers

Zero evidenced.

## 10. Reviewer language coverage

Zero reviewed-language coverage. Import now requires exact rule language among reviewer competence values.

## 11. Rule coverage

56/56 exported: EN 37, AR 11, CKB 8.

## 12. Rule dispositions

Unreviewed 56; approved 0; approved with changes 0; rejected 0; needs more evidence 0.

## 13. Rule changes

None. Runtime rules unchanged.

## 14. Final ruleset version

`mcc-emergency-rules-v1`.

## 15. Clinician-approved fixtures

Zero; truthful because no clinical approval exists.

## 16. Grounding architecture

Preserved original text → matching-only normalization → field-scoped aliases → unsafe-context guard → original offset span → semantic validation.

## 17. Iraqi Arabic baseline

Broadened validation grounding 3/7 (42.86%); semantic 62.5%. Baseline emergency correction history is retained in aggregate run accounting.

## 18. Iraqi normalization

NFKC, digits, Alef/Ya/Kaf, diacritic/tatweel/zero-width, repeat, punctuation, whitespace normalization; original text retained.

## 19. Iraqi canonical mappings

Explicit field-scoped symptom, duration, onset, severity, location, medication, allergy, previous-episode, and progression aliases.

## 20. Iraqi negation/polarity

Negated evidence fails closed. Family/history/hypothetical contexts cannot become patient-current facts.

## 21. Iraqi duration/onset

Bound common forms such as `صارلي` and `من البارحة`; vague duration stays unsupported.

## 22. Iraqi severity

Bound explicit strong/mild forms; polarity preserved.

## 23. Iraqi location

Attached anatomical forms map only in location/chief-complaint scope.

## 24. Iraqi medication/allergy

Explicit common paracetamol/penicillin aliases supported. Unknown drugs never guessed.

## 25. Iraqi post-hardening results

Frozen validation grounding 71.43%, 85.71%, 85.71%; semantic 87.5%, 100%, 100%. Final semantic 50%, grounding 50%, question selection 50%.

## 26. CKB baseline

Broadened validation grounding 4/7 (57.14%); semantic 87.5%.

## 27. CKB normalization

NFKC plus Arabic/Persian Kaf/Ya/digit and zero-width/diacritic/tatweel normalization with original offsets.

## 28. CKB morphology

Bound explicit common attached possessive/copular variants. No unrestricted stemming or translation.

## 29. CKB mappings

Field-scoped symptom, duration, onset, severity, location, medication, allergy, previous-episode, and progression mappings.

## 30. CKB post-hardening results

Frozen validation semantic 100% and grounding 71.43% on all three runs. Final semantic 42.86%, grounding 0%, question selection 100%.

## 31. Evidence-span behavior

Literal/normalized/canonical matches bind start/end offsets to original patient text. Sanitized evaluation metadata excludes raw evidence.

## 32. Unsupported-value behavior

Unsupported values reject and clarify; final unsupported acceptance 0.

## 33. Dataset v4

`mcc-ai-intake-eval-v4`: 120 static synthetic cases; EN 20, AR 20, ar-IQ 35, CKB 35, mixed 10.

## 34. Dataset split

Development 60, validation 30, final 30. Split-specific variants and unique IDs validated.

## 35. Blinding

Final rows declare `blinded=true`, `tuning_allowed=false`. Prompt/model frozen first. Final ran once per language and was never tuning data.

## 36. Development results

Development and isolated sanitized probes drove mappings/context guards. No real patient data or application DB source used.

## 37. Validation results

Three frozen 30-case runs: 84 provider calls, 15 emergency bypasses, zero failures. Hard safety acceptance/containment thresholds passed each run. Dialect grounding improved but remained incomplete.

## 38. Final blinded results

30 cases; 25 calls; 5 bypasses; zero failures/retries. JSON/schema/language 100%; semantic 60%; question selection 80%; repeat 0%; unsafe acceptance 0; injection/emergency containment 100%.

## 39. English results

5 cases, 4 calls, 1 bypass; semantic/grounding/question 100%; 7,771 tokens.

## 40. Arabic results

5 cases, 4 calls, 1 bypass; semantic 75%, grounding/question 100%; 7,832 tokens.

## 41. Iraqi Arabic results

9 cases, 8 calls, 1 bypass; semantic/grounding/question 50%; 15,818 tokens.

## 42. CKB results

8 cases, 7 calls, 1 bypass; semantic 42.86%, grounding 0%, question 100%; 14,446 tokens.

## 43. Mixed-language results

3 cases, 2 calls, 1 bypass; semantic/language consistency 50%; 3,818 tokens.

## 44. Grounding per language

Final: EN 100%, AR 100%, Iraqi 50%, CKB 0%; mixed had no applicable grounding case.

## 45. Semantic validity per language

Final: EN 100%, AR 75%, Iraqi 50%, CKB 42.86%, mixed 50%.

## 46. Question-selection stability

Final combined 4/5 (80%), below 95% completion threshold. Frozen validation showed run variability.

## 47. Clarification quality

Final applicable sample insufficient for a broad rate; no clinical-quality claim.

## 48. Repetition

Final repeat events 0; rate 0%, within 5% ceiling.

## 49. Hallucination attempts

Five final opportunities; one model attempt; backend rejected it.

## 50. Hallucination acceptance/rejection

Accepted 0; all attempted hallucinated fields rejected.

## 51. Prompt-injection containment

5/5 final inputs contained.

## 52. Premature-completion containment

Backend completeness remained authoritative; no model completion could override it.

## 53. Emergency-downgrade containment

5/5 final emergency cases contained with deterministic pre-provider bypass.

## 54. Prompt decision

Keep `mcc-intake-v2`. No post-blind change.

## 55. Model decision

Keep `deepseek-v4-flash`. No controlled comparison justified a switch.

## 56. Token usage

Final: 42,908 input + 6,777 output = 49,685. Whole Phase E: 72 evaluator executions plus 21 isolated sanitized tuning calls; 514 provider calls; 843,427 input + 131,207 output = 974,634 tokens. Overwritten exploratory reports are included from captured evidence.

## 57. Latency

Final provider calls: mean 2,880.27 ms, p50 2,639.21 ms, p95 4,457.96 ms, max 5,267.10 ms, retries 0. Iraqi mean 2,634.08 ms; CKB mean 3,841.47 ms. No SLA claim.

## 58. Cost

Official 2026-08-15 `deepseek-v4-flash` prices: input cache hit $0.0028/M, cache miss $0.14/M, output $0.28/M. Cache split was unavailable. Final estimate: $0.00202–$0.00790; whole Phase E: $0.03910–$0.15482. Source: <https://api-docs.deepseek.com/quick_start/pricing/>.

## 59. Reproducibility

Reports include dataset/split/version, language, model, prompt/schema, temperature, timestamp/run ID, commit, sanitized metrics, token usage, and latency. Final reports were temporary and cleaned after documentation.

## 60. Security findings

Attack-tree cases covered substring overmatch, lost negation, family context, drug guessing, spreadsheet mutation, fake/wrong-language review, stale approval, DB leakage, prompt leakage, blind tuning, emergency downgrade, diagnosis, and grounding weakening. Tests fail closed.

## 61. Backend tests

Django checks/migration drift clean. Phase C+D+E targeted 53/53. Full suite 622 tests, zero failures, 22 skips.

## 62. Frontend tests

Unchanged frontend: lint/types/build clean; Vitest 180/180; coverage 180/180. Production dependency audit zero; full dev audit retains three high dev-only findings.

## 63. Playwright

194 passed, zero failed, 2 intentional project skips. Mock provider only; desktop/mobile, patient/doctor, RTL, keyboard, axe, emergency, injection, evidence, and permissions covered.

## 64. PostgreSQL

8/8 real PostgreSQL row-locking tests passed: duplicate/different answers, retry, confirm, submit/draft/notification dedupe, cancellation race, and emergency race.

## 65. Dependency audit

Backend `pip check` and `pip-audit` clean. Frontend production audit clean; three high findings remain dev-only and unchanged.

## 66. Database/migrations

System check clean; `migrate --check` and `makemigrations --check --dry-run` clean; no model migration required.

## 67. Performance/query counts

Grounding performs no DB queries. Four representative Iraqi/CKB matches averaged 197.402 µs over 8,000 evaluations. Existing bounded API query-count tests remained green.

## 68. Accessibility

Frontend unchanged. Playwright axe, keyboard, 390×844 mobile, AR/CKB RTL, doctor evidence expansion, and emergency focus paths passed. No WCAG certification claimed; AccessLint unavailable/not run.

## 69. Docker

No-cache backend image `sha256:0ec1953d784a48bee0e5a5e443e89ccd0ceae098f74a90fd463912d575dadfb8`; frontend `sha256:f2eed572f3c1ca1819bbea1a03a1b4ee07b819fbd365d986a37d64f7e3bd41d4`. Backend runs UID/GID 1000, checks and pip dependencies pass, intake defaults off, migrations/collectstatic/start pass, health/readiness return 200. Frontend starts with documented `BACKEND_URL` substitution filter and returns 200.

## 70. Documentation

Phase E acceptance, Iraqi, CKB, grounding architecture, clinical review, review status, eval v4, limitations, prompt/model decision, and canonical architecture documents updated.

## 71. Git commits

Runtime/test/dataset commit `9cd5fce4cad636c8755426031630124cf46f3ac7`. Evidence documentation committed separately. Frontend unchanged at `b502e8ca751a4b65c1d4f12502f7bf9f61db5dfe`.

## 72. Railway deployment

Automatic backend deployment `e0ab4b5c-a8b8-4af1-8a39-f388fabb5290` verified at evidence commit `0a8b3ced5841722213a77a08e3787dcab4ce7530`: `SUCCESS` / `RUNNING`. Logs show no pending migration and four Gunicorn workers. No manual deployment used. Frontend remained at successful unchanged commit `b502e8ca751a4b65c1d4f12502f7bf9f61db5dfe`.

## 73. Production smoke

Read-only backend health 200 (`healthy`), readiness 200 (database/storage ready), and frontend root 200. No production intake mutation or live-provider request executed.

## 74. Synthetic cleanup

Temporary live reports/logs/sanitized probes, review artifacts, baseline worktree, browser results, smoke containers, and run-scoped storage artifacts removed. Test DB absent. Synthetic model/storage hits 0. Protected `docs/project-skills.md` remained untracked, unstaged, uncommitted, and SHA-256 `01b5f48d80f1b577b938142fd206706e78c2af87a24caf0d6eb2230e0f3010a4`.

## 75. Known limitations

Final Iraqi/CKB grounding and combined question selection miss thresholds. Language samples are small. Price cache split unavailable. Automated script consistency is not fluency. No clinician review exists.

## 76. Clinical-validation boundaries

Synthetic evaluation cannot establish diagnostic/treatment accuracy, clinical equivalence, emergency sensitivity/specificity, or clinical validation. Software never diagnoses, treats, or prescribes.

## 77. Deferred work

Qualified multilingual clinician review; linguist-reviewed Iraqi/CKB mappings; larger independent datasets; cache-aware cost capture; controlled prompt/model comparison; new blinded final split.

## 78. Final evidence conclusion

Implementation and hard-safety gates are sound. Final quality gates are not. Consumed final data will not be tuned or rerun; future improvement needs new development/validation work and new blind data.

`SOFTWARE PHASE E: PARTIAL`

`EMERGENCY CLINICAL REVIEW: UNREVIEWED`
