# Patient Doctor Discovery

## Scope

Patient discovery uses `/app/patient/doctors` and
`/app/patient/doctors/:doctorId`. Public doctor APIs return only approved
profiles. Consultation creation uses `/app/patient/consultations/new`.

## Rules

- Approved, active, accepting doctor: discoverable and selectable.
- Approved, active, non-accepting doctor: discoverable with unavailable state;
  consultation creation blocked server-side.
- Pending, suspended, rejected, or inactive doctor: not patient-discoverable.
- Inactive specialty: excluded from discovery and creation.
- Search, specialty, language, availability, ordering, and pagination are
  server-authoritative.
- License numbers, approval notes, identity documents, private contact fields,
  and storage metadata never enter patient serializers.
- Create request uses a client request ID. Duplicate submission returns one
  consultation. Doctor/specialty state is revalidated inside transaction.

## Acceptance Evidence

- Backend: `tests/test_patient_phase_b.py`
- Frontend: `src/test/patientPhaseB.test.ts`
- Browser: `e2e/patient-phase-b.spec.ts`
- Doctor list ceiling: 5 queries.
- Doctor detail ceiling: 3 queries.
- Consultation creation ceiling: 14 queries.

No booking, payment, prescription, video, or appointment scheduling behavior
is implied.
