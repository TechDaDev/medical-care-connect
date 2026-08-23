# AI Intake Phase F Root Cause

## Phase E classification

Iraqi failures mixed provider extraction, grounding false negatives, and evaluator defects. Four applicable final cases scored 2/4: fixture/evaluator/model behavior each contributed. CKB scored 0/4 because canonical rewriting and Unicode/segmentation mismatches made supported values fail evidence checks. These were safe false rejections, not unsafe acceptances.

Question selection scored 80% because provider target choice remained model-driven and one final case selected the wrong field. Evaluator also depended on fixture-supplied missing/target labels, so it did not measure backend state independently.

## Corrective design

- Normalize NFKC, bidi/zero-width controls, Arabic letter variants, digits, punctuation, and whitespace without erasing Kurdish distinctions or negation.
- Recognize bounded, field-scoped Iraqi and CKB phrases; derive original-text spans for every accepted value.
- Keep medication and allergy validation stricter than ordinary free text.
- Treat vague numeric language as uncertain/unsupported; allow explicit structured numeric transforms.
- Apply clause-local negation, family/history attribution, and latest explicit correction rules.
- Derive allowed and preferred question targets from deterministic completeness state. Provider may supply wording only for preferred target; backend otherwise falls back.
- Score accepted backend target separately from raw provider target and derive evaluation context from backend state.

No diagnosis, treatment, prescribing, autonomous triage, emergency authority, or automatic record finalization was added.
