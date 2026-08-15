# AI Intake Language Grounding Architecture

Status date: 2026-08-15

## Authority and flow

Patient message → preserved original text → language-aware normalization for matching → field-scoped literal/normalized/canonical match → unsafe-context guard → original-text evidence span → semantic validator.

`GroundingEvidence` records classification (`literal`, `normalized`, `canonical`, `structured`, or `unsupported`) and optional original-text offset span. Runtime persistence continues to use source message UUIDs and original content. Evaluation reports retain only sanitized field/classification/message-ID/offset data; raw evidence and provider output are excluded.

## Constraints

- Backend remains sole authority for accepted fields, evidence ownership, completeness, emergency state, confirmation, and submission.
- Normalization can prove existing evidence; it cannot create evidence.
- Aliases are explicit and field-scoped. No global dialect acceptance.
- Token boundaries prevent substring overmatch.
- Negation, family, historical, and hypothetical context prevent unsafe canonical matches.
- Unsupported values fail closed.
- No patient/session/consultation ORM source is permitted in live evaluation.

Grounding is deterministic technical validation, not clinical interpretation, dialect certification, or diagnostic reasoning.
