# AI Intake Final Safety Model

Status date: 2026-08-15

## Controls

- Deterministic emergency screening precedes provider calls. Emergency-positive v3 cases bypassed provider 100%.
- Strict schema forbids unknown keys/fields and has no diagnosis, treatment, or prescription authority.
- Evidence UUID ownership plus literal, normalized, or field-scoped canonical grounding is mandatory.
- Unsupported facts are rejected; safe rejection triggers clarification instead of persistence.
- Deterministic completeness independently blocks premature review, confirmation, and submission.
- Live evaluation requires explicit CLI and environment flags, static synthetic input, non-production environment, official HTTPS endpoint, case cap, `/tmp` JSON output, and no patient/consultation/database source.
- Normal tests, CI, and Playwright use deterministic providers and do not call DeepSeek.
- Review CSV is non-executable. Import rejects unknown/duplicate rules, wrong versions, pattern/category/language/severity/enablement mutations, invalid dispositions, and missing reviewed-decision evidence.

## Threat closure

1. DB patient access: evaluator has no ORM imports or `.objects` access; database-source option is refused.
2. Real evaluation data: top-level and per-case `synthetic=true`; forbidden identifier keys rejected.
3. Provider key logging: sanitized reports contain no configuration or raw output.
4. Raw response commit: reports constrained to `/tmp`; cleanup required.
5. Final-set tuning: separate blinded file, `tuning_allowed=false`, explicit final flag, one provider run only.
6. CSV executable mutation: exact runtime properties compared and mutation rejected.
7. Forged reviewer: software validates required metadata but cannot establish real-world identity; operational qualification verification remains external.
8. Wrong ruleset: rejected.
9. Rejection shown as approval: disposition preserved explicitly.
10. Changed rule inherits approval: exact rule ID/version binding; material runtime change requires version/re-review.
11. Grounding relaxation: aliases are field-scoped and every mapped phrase must occur in evidence; invented medication/allergy/surgery/duration/pregnancy/diagnosis tests reject.
12. Dialect mapping invents meaning: only explicit phrase-to-canonical mappings accepted; uncertain forms remain rejected.
13. Diagnosis output: prohibited semantic content rejected and no schema authority exists.
14. Completeness bypass: evaluator and runtime use deterministic completeness engine.
15. Emergency downgrade: provider bypass and backend state are authoritative.
16. Playwright live calls: mock-provider configuration remains mandatory.

## Boundaries

These are software containment results, not clinical sensitivity, specificity, diagnostic accuracy, treatment accuracy, prescribing accuracy, clinical equivalence, or clinical validation.

