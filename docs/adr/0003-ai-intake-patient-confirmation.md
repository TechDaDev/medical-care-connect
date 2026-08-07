# ADR 0003: AI intake patient confirmation

- Status: accepted
- Date: 2026-08-07

## Context

Intake must not be submitted to a doctor on AI-extracted information alone.
Patients must be able to review a structured summary, correct extraction, mark
fields unknown or declined, and explicitly confirm before submission. Without
this, AI-extracted values could be treated as patient-authorized facts.

## Decision

Add a mandatory review → correction → confirmation → submission workflow on the
deterministic backend:

- Review: `GET /api/intake/sessions/<id>/review/` returns a patient-safe
  structured summary with sections, statuses, source, evidence message ids, and
  confirmation eligibility. Hidden provider data and hidden prompts are never
  included.
- Corrections: `PATCH /api/intake/sessions/<id>/corrections/` accepts an
  allowlist-checked map of field patches. A corrected value replaces the AI
  extraction (source becomes `patient_correction`); it never rewrites the
  original patient message. Protected/unknown fields are rejected. Audit records
  only changed field names.
- Confirmation: `POST /api/intake/sessions/<id>/confirm/` requires
  `{"confirmation": true, "expected_updated_at", "client_request_id"}`. Requires
  an `awaiting_patient_review` state, the deterministic completeness gate, and
  optimistic concurrency. Stores a confirmation snapshot, marks fields
  `confirmed_by_patient`, records exactly one audit event, and does not notify
  the doctor until final submission. Idempotent via `client_request_id`.
- Submission: `POST /api/intake/sessions/<id>/submit/` requires `confirmed`
  state, the completeness gate, optimistic concurrency, and atomically creates
  exactly one intake-derived draft, transitions the consultation to
  `doctor_review`, sends one doctor notification, and audits once.
- Returning to questioning: an answer submitted while in a reviewable state
  transitions the session back to `in_progress`.

## Consequences

No intake reaches the doctor without explicit patient confirmation of reviewed
information. Confirmation snapshots provide an immutable record of what the
patient accepted. Corrections are provenance-tracked and patient-auditable.
