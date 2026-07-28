# Patient Consultation Lifecycle

## Lifecycle

Supported statuses:

`draft`, `submitted`, `accepted`, `intake_in_progress`,
`intake_completed`, `doctor_review`, `awaiting_patient_response`,
`awaiting_doctor_response`, `under_review`, `follow_up_required`,
`physical_visit_required`, `transferred`, `completed`, `cancelled`, and
`emergency_escalated`.

Patient list and detail are available at `/api/consultations/` and
`/api/consultations/:id/`. Server emits timeline and available-action policy.
Client does not infer permission from status.

## Cancellation

`POST /api/consultations/:id/cancel/` requires ownership, reason, and expected
status. Transaction acquires PostgreSQL row lock. State mismatch and prohibited
states return 409. Repeating an already completed cancellation is idempotent.
Only first transition creates cancellation audit and doctor notification.

Real-lock regression:

```bash
DJANGO_SETTINGS_MODULE=config.settings.test_postgres \
  .venv/bin/python manage.py test \
  tests.test_patient_phase_c.PatientCancellationConcurrencyTests
```

## Intake and Messaging

Patient-safe intake responses exclude prompts, provider/model data, token
counts, emergency rule internals, and collected private structure. Intake
answers and messages use client request IDs. Conversation reads never mark
patient-authored messages as incoming/read.

## Evidence

- Backend: `tests/test_patient_phase_c.py`
- Frontend: `src/test/patientPhaseC.test.tsx`
- Browser: `e2e/patient-phase-c.spec.ts`
- List/detail ceiling: 8 queries each.
