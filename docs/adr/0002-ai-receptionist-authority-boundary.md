# ADR 0002: AI receptionist authority boundary

- Status: accepted
- Date: 2026-08-07

## Context

The AI intake receptionist interviews a patient before doctor review. Without
an explicit authority boundary, the LLM could independently complete or submit
an intake, fabricate facts, expose hidden prompts, or write content into
doctor-authored medical fields.

## Decision

The deterministic Django backend is the sole authority for: session ownership,
state transitions, idempotency, sequence allocation, emergency screening and
escalation, completion gates, patient confirmation, submission, consultation
status, record-draft creation, notifications, and audits. DeepSeek may only
assist with conversational wording, structured extraction, missing-field
suggestions, and summarizing patient-reported content. DeepSeek never controls
authorization, emergency override, completion/submission state, diagnosis,
treatment, record content, doctor assignment, or patient confirmation.

Concrete enforcement:

- `transition_state()` centralizes legal intake status transitions; the frontend
  and provider never write arbitrary status values.
- `evaluate_completeness()` is the only authority for `can_generate_review_summary`,
  `can_confirm`, and `can_submit_to_doctor`. The provider's `propose_review` is
  advisory and always re-checked by the backend gate.
- Deterministic emergency screening (`screen_patient_input`) runs before any
  normal-flow persistence and before any provider call. The provider's
  `emergency_signal` may only increase caution; it can never clear a
  deterministic emergency.
- Confirmation (`confirm_intake`) and submission (`submit_intake`) are
  patient-only, idempotent, optimistic-concurrency-guarded service calls that
  require reviewable/confirmed states and the deterministic completeness gate.

## Consequences

The AI cannot force completion or submission. Emergency handling never depends
on the LLM. Hallucinated or unsafe provider output is rejected by schema and
semantic validation before it enters authoritative state. This boundary is
regression-tested across the Phase A suite.
