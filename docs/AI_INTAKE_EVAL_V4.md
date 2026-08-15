# AI Intake Evaluation Dataset v4

Status date: 2026-08-15

Dataset version: `mcc-ai-intake-eval-v4`. All cases are static and synthetic.

## Composition

- 120 cases: development 60, validation 30, final blinded 30.
- Languages: EN 20, AR 20, Iraqi Arabic (`ar-IQ`) 35, Kurdish Sorani (`ckb`) 35, mixed 10.
- Categories cover grounding, Unicode/morphology, negation/polarity, family/history/hypothetical context, temporal/severity/location, medication/allergy, question choice, repetition, unsupported values, hallucination, injection, premature completion, and emergency downgrade.
- Each split uses distinct language variants. Final rows declare `blinded=true` and `tuning_allowed=false`.

## Integrity

Evaluator verifies version, case count, split membership, language distribution, unique IDs, synthetic markers, expected metadata, and final-blind flags. Final data cannot come from a database or application identifier. Reports are sanitized and temporary.

Development and validation supported hardening. Prompt `mcc-intake-v2` and model `deepseek-v4-flash` were frozen before final exposure. Final split ran once per language, was not rerun, and must never become tuning data.

## Final blinded result

30 cases; 25 provider calls; 5 deterministic emergency bypasses; 0 provider failures/retries. JSON/schema validity and language consistency were 100%. Combined semantic pass was 15/25 (60%); question selection was 4/5 (80%); repetition 0%. Unsupported acceptance 0, hallucinated acceptance 0, injection containment 5/5, emergency-downgrade containment 5/5.

Per-language semantic/grounding: EN 100%/100%; AR 75%/100%; Iraqi 50%/50%; CKB 42.86%/0%; mixed semantic 50% with no applicable grounding item. These quality failures prevent `SOFTWARE PHASE E: COMPLETE` despite hard-safety containment.
