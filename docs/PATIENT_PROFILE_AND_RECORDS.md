# Patient Profile and Records

## Profile

`GET/PATCH /api/patients/me/` serves authenticated patient profile only.
Mutable groups cover demographics, preferences, address, emergency contact,
and patient notes. Role, approval, ownership, audit, and staff fields are
immutable. Profile completion is derived from saved server data.

## Medical Records

- List: `GET /api/patients/me/medical-records/`
- Patient detail: `GET /api/patients/me/medical-records/:id/`
- Shared safe record detail: `GET /api/medical-records/:id/`

Every lookup enforces patient ownership. Patient payload excludes doctor notes,
internal additional notes, intake internals, staff metadata, and storage paths.
Records are not patient-editable. Empty and paginated states are supported.

## Evidence

- Backend: `tests/test_patient_phase_d.py`,
  `tests/test_patient_phase_c.py`
- Frontend: `src/test/patientPhaseD.test.tsx`
- Browser: `e2e/patient-phase-d.spec.ts`
- Profile ceiling: 5 queries.
- Record list ceiling: 7 queries.
- Record detail ceiling: 5 queries.
