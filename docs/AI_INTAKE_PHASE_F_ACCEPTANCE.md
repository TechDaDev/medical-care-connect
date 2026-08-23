# AI Intake Phase F Acceptance

Status date: 2026-08-23. Evidence is software evaluation on synthetic data only.

## 1. Executive summary
Safety gates held and deterministic question selection recovered. Iraqi/CKB final grounding missed 80%; phase remains partial.

## 2. Software Phase F status
`PARTIAL`.

## 3. Emergency clinical-review status
`UNREVIEWED`; no new clinician evidence.

## 4. Skills used
Caveman communication plus relevant acceptance, evaluation, architecture, security, performance, Django, privacy, Docker, Railway, Playwright, and i18n skills. `prompt-engineering-patterns` was unavailable and not installed.

## 5. Baseline commits
Backend `2bbc09c02c4ffe9d5aa892c6aef277e48b3763f0`; frontend `b502e8ca751a4b65c1d4f12502f7bf9f61db5dfe`.

## 6. Codebase-memory pre-change findings
Graph traces found model-driven target selection, generic evidence overlap, normalization gaps, and fixture-coupled scoring.

## 7. Codebase-memory post-change findings
Post-change graph verification is recorded in final release evidence.

## 8. Phase E failure classification
Iraqi: model, grounding, evaluator, fixture mix. CKB: model canonical rewrite plus grounding/evaluator mismatch. Question selection: provider target and scorer defects.

## 9. Iraqi failure root causes
Insufficient field aliases, structured numeric transforms, correction/negation scope, and provider canonical rewriting.

## 10. CKB failure root causes
Unicode variants, simplistic segmentation, evidence-span mismatch, canonical rewrite, and evaluator defects.

## 11. Question-selection root causes
Provider owned target; prompt context and fixture-bound scorer did not enforce deterministic missing-field priority.

## 12. Grounding architecture before
Generic normalization and lexical overlap produced safe false negatives.

## 13. Grounding architecture after
NFKC/token spans → field-scoped aliases/numeric transforms → clause safety → evidence classification → fail-closed acceptance.

## 14. Iraqi normalization
Alef/Ya, digits, punctuation, whitespace, bidi, zero-width, and bounded spelling variants handled; negation retained.

## 15. Iraqi lexical mappings
Mappings are field-scoped; no unrestricted translator or diagnosis dictionary.

## 16. Iraqi duration handling
Explicit day/week/month forms support structured numeric grounding; vague forms cannot become exact.

## 17. Iraqi onset handling
Onset remains distinct from duration and requires onset evidence.

## 18. Iraqi severity handling
Explicit contextual severity terms supported; intensifiers alone do not imply numeric pain.

## 19. Iraqi negation
Clause-local direct/double negation, correction, family, and history protections tested.

## 20. Iraqi location handling
Explicit body-area phrases map only to location, never pathology.

## 21. Iraqi medication/allergy handling
Exact aliases only; unknown drugs fail closed; adverse effects do not become allergy.

## 22. Iraqi corrections
Latest explicit safe correction wins; source messages remain immutable.

## 23. CKB Unicode normalization
NFKC, Kaf/Ya compatibility, digits, punctuation, bidi, zero-width handled; Kurdish distinctions preserved.

## 24. CKB tokenization
Unicode span scanning replaces whitespace-only matching.

## 25. CKB morphology
Bounded clitic/possessive phrase variants supported through field rules.

## 26. CKB field mappings
Complaint, symptom, timing, severity, location, medicine, allergy, negation, family, and correction only.

## 27. CKB evidence spans
Accepted values retain original-text start/end spans and message ownership internally.

## 28. CKB negation
Polarity and family attribution cannot be erased by normalization.

## 29. Mixed-language grounding
Arabic/CKB with explicit English medication or duration terms supported conservatively.

## 30. Structured numeric grounding
Exact numeric/unit transforms accepted; vague quantities rejected.

## 31. Unsupported-value behavior
Final unsupported acceptances: 0; attempts: 7; all rejected.

## 32. Question-target architecture
Backend owns field target; provider owns wording only when target matches.

## 33. Allowed-next-fields behavior
Ordered deterministic allowlist excludes completed and lower-priority optional fields.

## 34. Preferred-next-field behavior
First blocking registry-priority field is preferred; review/emergency produces null.

## 35. Clarification behavior
Validation runs: 5/5 valid clarifications each; final had no applicable clarification denominator.

## 36. Repetition behavior
Final unnecessary repetition 0%.

## 37. Prompt decision
Create v3 because provider canonical rewriting remained after server target enforcement; exact-copy instruction added.

## 38. Prompt version
`mcc-intake-v3`; response schema `mcc-intake-v2`.

## 39. Model decision
`KEEP CURRENT MODEL`; defects were primarily authority/grounding problems.

## 40. Model version
`deepseek-v4-flash`.

## 41. Dataset v5
150 synthetic cases: EN 20, MSA 20, Iraqi 45, CKB 45, mixed 20.

## 42. Dataset independence check
Against 220 v3/v4 cases: exact 0, near ≥0.85 0, removed 0.

## 43. Dataset split
Development 70, validation 40, final 40.

## 44. Blinding integrity
Final marked blinded/non-tunable, generated once after freeze, executed once. Procedural generator blinding is not independent human blinding.

## 45. Development results
Five report runs: 227 provider calls, 25 bypasses, 0 failures/retries. Last full Iraqi grounding 86.67%; post-v3 CKB-focused grounding 86.67%; accepted target 100%.

## 46. Validation run 1
Grounding 69.57%; Iraqi 71.43%; CKB 71.43%; target 100%; 38 calls/2 bypasses.

## 47. Validation run 2
Grounding 60.87%; Iraqi 71.43%; CKB 71.43%; target 100%; 38 calls/2 bypasses.

## 48. Validation run 3
Grounding 56.52%; Iraqi 57.14%; CKB 71.43%; target 100%; 38 calls/2 bypasses.

## 49. Final blinded results
40 cases, 36 calls, 4 bypasses; grounding 66.67%, semantic 80.56%, target 100%; final executed once.

## 50. English results
Grounding 66.67%; semantic 80%; 5 calls/1 bypass.

## 51. Arabic results
Grounding 33.33%; semantic 60%; 5 calls/1 bypass.

## 52. Iraqi Arabic results
Grounding 62.5%; semantic 72.73%; 11 calls/1 bypass.

## 53. CKB results
Grounding 75%; semantic 90.91%; 11 calls/1 bypass.

## 54. Mixed-language results
Grounding 100%; semantic 100%; 4 calls/0 bypasses.

## 55. Iraqi grounding before/after
Phase E final 50% → Phase F final 62.5%; improved but below 80%.

## 56. CKB grounding before/after
Phase E final 0% → Phase F final 75%; improved but below 80%.

## 57. Semantic validity per language
EN 80%, MSA 60%, Iraqi 72.73%, CKB 90.91%, mixed 100%.

## 58. Question-selection before/after
Phase E final 80% → Phase F accepted backend target 100%; raw provider target 50%.

## 59. Clarification quality
Final not applicable; validation applicable clarifications all valid.

## 60. Repeat rate
Final 0%; threshold ≤5% passed.

## 61. Hallucination attempts
Final evaluator recorded 5 opportunities; provider generated 0 accepted attempts.

## 62. Hallucination rejected/accepted
Rejected 0 because no provider attempt; accepted 0.

## 63. Prompt-injection attempts
Final included 5 injection inputs.

## 64. Prompt-injection containment
100%; no hidden prompt or provider secret leakage.

## 65. Premature-completion containment
100%; backend completeness remains authoritative.

## 66. Emergency-downgrade containment
Four final emergency inputs; 100% contained and provider bypassed.

## 67. JSON validity
100% final.

## 68. Schema validity
100% final.

## 69. Language consistency
100% final.

## 70. Provider calls/failures/retries
Development 240 total calls: 227 across five reports plus 13 bounded diagnostics. Validation 38×3; final 36. Report bypasses 25/2×3/4; failures 0; retries 0. Diagnostic calls were outside report token aggregates.

## 71. Token usage
Development 407,224 input/61,899 output; validation 210,408/31,795; final 66,316/9,808. Reported total 683,948 input, 103,502 output, 787,450 total.

## 72. Latency
Final mean 2965.96 ms, p50 2917.13, p95 4093.59, max 4381.63; Iraqi mean 2876.41, CKB mean 3474.29; retries 0.

## 73. Cost
DeepSeek V4 Flash pricing checked 2026-08-23: $0.0028/M cache-hit input, $0.14/M cache-miss input, $0.28/M output. Unknown cache split gives reported-run estimate $0.0309–$0.1247.

## 74. Grounding-processing performance
20,000 local calls: mean 0.2296 ms, p95 0.3968 ms, max 0.8800 ms; provider latency excluded.

## 75. Security findings
Fourteen required attack paths closed by field scoping, clause attribution, exact drug policy, deterministic target enforcement, emergency bypass, and synthetic evaluator guards.

## 76. Backend tests
Focused Phase F/A–E tests passed. Full backend: 641 passed, 22 skipped, 0 failed in 466.449 seconds.

## 77. Frontend tests
Lint/types/build passed; Vitest 180/180 twice, coverage statements 60.30%, branches 57.22%, functions 57.20%, lines 62.25%.

## 78. Playwright
Complete deterministic matrix: 10/10 specs passed, representing 73 scenarios on desktop and mobile; accessibility checks included.

## 79. PostgreSQL
Eight concurrency tests passed: duplicate/different answers, retry, confirmation, submission/dedupe, and emergency race.

## 80. Dependency audit
`pip check` clean; `pip-audit` clean after Django 5.2.17/sqlparse 0.6.0; frontend runtime audit 0 vulnerabilities.

## 81. Database/migrations
System check and migration generation clean; local PostgreSQL existing pending migrations applied; `migrate --check` clean.

## 82. Query counts
Existing ceilings retained: start ≤20, answer ≤30, doctor detail ≤4; grounding adds no ORM work.

## 83. Accessibility
Playwright axe WCAG A/AA/2.1AA checks passed in terminal matrix.

## 84. Docker
Backend/frontend no-cache builds passed. Backend image `sha256:8f42d762a9cc7fa545d14a68b08cdf55b226109d9ddd9538e16aebf0cac5af06` ran as UID/GID 1000 against ephemeral PostgreSQL: health/readiness, Django check, `pip check`, and migration check passed. Frontend image `sha256:f06f93878c6c79383a1c5d1075ae5c27907d6d698a0fca9e36833280f59ddb8f` served root and proxied backend health with HTTP 200. Smoke containers, tmpfs database, and network were removed.

## 85. Documentation/ADR
Seven Phase F documents, architecture update, and ADR 0008 describe grounding, evaluation, limits, and deterministic authority.

## 86. Git commits
Backend implementation commit: `53aa35d`. Frontend E2E alignment commit: `264b699`. Dataset/documentation remains a separate reviewed backend commit containing this report; full hashes are recorded in final release evidence after commit creation.

## 87. Railway deployment
Read-only automatic deployment evidence recorded after push; no manual deploy.

## 88. Production read-only smoke
Health, readiness, frontend root, and safe anonymous protected-route evidence recorded after deployment.

## 89. Synthetic cleanup
Run-scoped E2E cleanup passed; raw evaluation and browser artifacts removed after evidence extraction. Protected file remains untracked, unstaged, uncommitted, hash unchanged.

## 90. Known limitations
Final Iraqi/CKB grounding below target; small subgroups; raw provider target 50%; generator blinding is procedural; cache split unknown.

## 91. Clinical-validation boundaries
No diagnostic, treatment, prescribing, emergency-performance, certification, doctor-equivalence, or clinical-validation claim.

## 92. Deferred work
Qualified multilingual clinician/linguist review, independently curated blinded set, more robust provider literal-copy behavior, and cache-aware cost capture.

## 93. Final evidence conclusion
Safety and deterministic target gates passed; grounding quality gates failed. Software status is partial. Clinical review remains unreviewed.

SOFTWARE PHASE F: PARTIAL

EMERGENCY CLINICAL REVIEW: UNREVIEWED
