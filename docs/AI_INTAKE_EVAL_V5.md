# AI Intake Evaluation v5

Dataset `mcc-ai-intake-eval-v5` contains 150 synthetic cases: English 20, Arabic MSA 20, Iraqi Arabic 45, Kurdish Sorani 45, mixed 20. Splits: development 70, validation 40, final blinded 40. Final metadata sets `blinded=true` and `tuning_allowed=false`.

Generator is independent of exposed Phase E cases. Normalized text comparison against 220 v3/v4 cases found zero exact duplicates and zero near duplicates at similarity ≥0.85; zero removals were needed. Final IDs/expected values were absent from development prompts, logs, examples, and tuning fixtures before freeze.

Evaluator derives missing fields and preferred target from deterministic backend state, never fixture target labels. Metrics separate expected recall, evidence grounding, semantic validity, unsupported acceptance, raw provider target, accepted backend target, clarification, repetition, emergency bypass, and format/language validity.

Live execution requires explicit flag, non-production environment, synthetic input, bounded cases, approved endpoint, and safe output path. Final was run exactly once after implementation, prompt, model, and dataset freeze. Raw provider responses are not committed.
