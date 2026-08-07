# AI Intake Patient Confirmation

Patients must review, correct, and explicitly confirm their intake before it is
submitted to the doctor. This is a mandatory, backend-enforced gate.

## Endpoints

| Action | Method/Path | Notes |
| --- | --- | --- |
| Review | `GET /api/intake/sessions/<id>/review/` | patient-safe structured summary |
| Corrections | `PATCH /api/intake/sessions/<id>/corrections/` | allowlist-checked field patches |
| Confirm | `POST /api/intake/sessions/<id>/confirm/` | `{confirmation:true, expected_updated_at, client_request_id}` |
| Submit | `POST /api/intake/sessions/<id>/submit/` | `{expected_updated_at, client_request_id}` |

## Review payload

Includes sections with per-field value/status/source/evidence ids, missing
blocking fields, uncertainty, confirmation and submission eligibility, and an
AI-assisted summary explicitly labeled "not clinically verified". Hidden
provider data, raw prompts, and raw provider responses are never included.

## Corrections

- Field names must be allowlisted.
- Status must be a valid status; corrected `answered` values require a value.
- Corrected values replace the AI extraction (`source=patient_correction`);
  original patient messages are never rewritten.
- Changing a field to `unknown` clears its stored value.
- Audit events record only changed field names — never content.

## Confirmation rules

- Consultation-owning patient only.
- Session must be in a reviewable state.
- Deterministic completeness gate must pass.
- `confirmation: true` is required.
- Optimistic concurrency via `expected_updated_at`; stale → 409 `stale_intake`.
- Idempotent via `client_request_id`.
- Stores a `confirmation_snapshot` and marks fields `confirmed_by_patient`.
- Exactly one audit event.
- No doctor notification at confirmation — only at final submission.

## Submission rules

- Patient-confirmed state required.
- Deterministic completeness gate.
- Atomic transaction with row locks on session and consultation.
- Creates exactly one intake-derived draft.
- Transitions consultation to `doctor_review` once.
- One doctor notification; one audit; authoritative response.

## Returning to questioning

An answer submitted while in a reviewable state transitions the session back to
`in_progress`, allowing the patient to supply missing information.

See `docs/adr/0003-ai-intake-patient-confirmation.md`.
