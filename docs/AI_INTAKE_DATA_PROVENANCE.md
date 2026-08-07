# AI Intake Data Provenance

Provenance answers: where did each fact come from, what evidence supports it,
and who confirmed it.

## Sources

Each intake field carries a `source`:

- `patient_message` — the patient said it directly.
- `patient_profile` — from the patient profile (reserved; not yet populated).
- `intake_extraction` — extracted by the AI from patient answers.
- `patient_correction` — the patient corrected/edited the value during review.

## Evidence

- Every AI extraction references `evidence_message_ids` — the patient messages
  that support it. These must belong to the session (semantic validation).
- Explicit/inferred extractions must be lexically grounded in the cited
  evidence, or they are rejected (hallucination guard).
- Explicit patient answers are never overwritten by inferred AI data.
- `confidence` (low/medium/high) is internal and never shown as clinical
  certainty.

## Confirmation

At confirmation, `confirmed_by_patient` is set on every accepted field, and a
`confirmation_snapshot` stores the accepted metadata, timestamps, and
prompt/schema versions. This snapshot is the authoritative record of what the
patient accepted.

## Doctor view

The doctor-safe projection shows, per field, the value, status, source, and
evidence message ids, plus patient-confirmed badge, submitted timestamp,
language, version metadata, uncertainty, missing/non-blocking information, and
an AI-assisted disclaimer.

## Medical-record draft separation

`generate_draft_from_intake`:

- populates a fixed patient-reported field map from confirmed intake values;
- stores the AI-assisted summary as labeled metadata
  (`not_clinically_verified: true`) and into `additional_notes` with a
  disclaimer prefix — never into a clinical field;
- leaves doctor-authored fields empty;
- never marks AI text as doctor-confirmed;
- creates exactly one draft per consultation.

See `docs/adr/0004-ai-intake-provenance-and-draft-generation.md`.
