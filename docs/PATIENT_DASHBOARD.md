# Patient Dashboard

## Scope

Patient landing route is `/app/patient`. API source is
`GET /api/patients/me/dashboard/`. Server derives all counts, recent activity,
unread state, actions, and paths from authenticated patient ownership.

## Contract

- Consultation summary covers total, active, awaiting-patient,
  awaiting-doctor, completed, and cancelled groups.
- Action queue exposes only patient-safe labels and application-relative paths.
- Recent consultations, medical records, messages, and notifications are
  ownership-filtered.
- Empty, loading, error, retry, desktop, mobile, English, Arabic, and Kurdish
  states remain supported.
- Dashboard never exposes descriptions, internal notes, AI internals, storage
  keys, staff data, or another patient's identifiers.

## Acceptance Evidence

- Backend: `tests/test_patient_phase_a.py`
- Frontend: `src/test/patientDashboard.test.tsx`
- Browser: `e2e/patient-phase-a.spec.ts`
- Accessibility: `e2e/patient-phase-e.spec.ts`
- Query ceiling: exactly 9 queries, asserted with populated and repeated data.

Dashboard is read-only. Links navigate to canonical patient routes; they do not
perform mutations.
