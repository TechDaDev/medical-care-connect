# AI Intake Completeness

`apps/ai_intake/services/completeness.py` implements the deterministic
completeness engine. The backend — not DeepSeek — decides when intake is
complete enough to review, confirm, and submit.

## Universally required (subject to product scope)

- chief complaint
- principal symptoms
- onset OR duration
- severity (or impact)
- relevant current medications
- relevant allergies
- relevant medical history
- emergency-screen completion
- patient review/confirmation

## Conditionally required

The AI may propose that a conditional field is relevant using an allowlisted
rule code (`localized_symptom`, `recurrence_relevant`, `pregnancy_relevant`,
`family_history_relevant`). The backend validates the rule against the registry
and only then adds the field to the required set.

## Non-blocking statuses

- `unknown` is allowed for `current_medications`, `allergies`,
  `past_medical_history` without blocking review.
- `declined` is allowed for optional fields (`social_history`,
  `substance_use`, `family_history`, `surgical_history`,
  `previous_tests_treatment`) and the unknown-allowed universals.

## Output

`evaluate_completeness(session)` returns a `CompletenessResult` with
`can_generate_review_summary`, `can_confirm`, `can_submit_to_doctor`,
`missing_blocking_fields`, `missing_non_blocking_fields`, question budget, and
a `reason_code` (`required_information_missing`,
`conditional_required_missing`, `question_budget_exhausted`,
`unknown_blocking_required_field`, `declined_blocking_required_field`,
`uncertain_blocking_required_field`, `review_ready`, `emergency_stopped`,
`cancelled`).

## Authority

- Provider `conversation_status=propose_review` is advisory only. The backend
  gate re-evaluates completeness and only transitions to
  `awaiting_patient_review` when `can_generate_review_summary` is true.
- `can_confirm` additionally requires `awaiting_patient_review` state.
- `can_submit_to_doctor` additionally requires `confirmed` state.
- Emergency and cancelled sessions can never be reviewed/confirmed/submitted.

See `docs/adr/0002-ai-receptionist-authority-boundary.md`.
