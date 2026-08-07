# ADR 0004: AI intake provenance and medical-record draft generation

- Status: accepted
- Date: 2026-08-07

## Context

AI-extracted intake facts must not be silently converted into doctor-authored
medical content. The medical-record draft generated from intake must preserve
the separation between patient-reported, AI-derived, and doctor-authored
information, and must carry provenance so the doctor sees the evidence behind
the summary.

## Decision

Provenance model on `AIIntakeSession`:

- `field_metadata` maps each allowlisted field to `{value, status, source,
  confidence, evidence_message_ids, confirmed_by_patient}`.
- `source` is one of `patient_message`, `patient_profile`, `intake_extraction`,
  `patient_correction`.
- `confidence` is an internal low/medium/high value used only for uncertainty
  labeling; it is never exposed as clinical certainty.
- Every AI extraction is semantically validated: evidence message ids must
  belong to the session, and explicit/inferred values must be lexically grounded
  in the cited patient messages (hallucination guard).

Draft generation (`generate_draft_from_intake`):

- Runs only from the deterministic submit flow after patient confirmation.
- Populates a fixed patient-reported field map from confirmed intake values.
- Stores the AI-assisted summary as labeled metadata
  (`provenance["ai_generated_summary"]` with `not_clinically_verified: true`)
  and into `additional_notes` prefixed with an explicit disclaimer — never into
  a clinical field.
- Leaves all doctor-authored fields (`assessment`, `working_diagnosis`,
  `treatment_plan`, `patient_instructions`, `clinical_outcome`, etc.) empty.
- Never marks AI text as doctor-confirmed. Creates exactly one draft per
  consultation via `get_or_create`.

Doctor-safe projection (`DoctorIntakeSerializer`) exposes: patient-confirmed
badge, submitted timestamp, language, prompt/schema versions, structured field
projection with provenance, uncertainty, missing/non-blocking information,
emergency state, and an AI-assisted disclaimer. It never exposes hidden prompts,
provider credentials, raw provider responses, or chain-of-thought.

## Consequences

Hallucinated facts cannot enter authoritative intake or the draft. AI-derived
content is always labeled and never merged into doctor-authored fields. The
doctor sees the evidence trail behind the summary. These guarantees are covered
by the record-draft separation and semantic-validation tests.
