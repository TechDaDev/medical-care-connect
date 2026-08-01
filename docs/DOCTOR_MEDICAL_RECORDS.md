# Doctor medical records

Doctor Phase C adds assigned-doctor record list, detail, draft creation, optimistic updates, finalization, and consultation outcomes.

## API

- `GET /api/doctors/me/medical-records/`: assigned records only; paginated; narrative-free list.
- `GET|PATCH /api/doctors/me/medical-records/{record_id}/`: separated patient-reported, intake-reference, AI-suggestion, and doctor-authored sections.
- `POST /api/consultations/{consultation_id}/medical-record/`: idempotent get-or-create.
- `POST /api/doctors/me/medical-records/{record_id}/finalize/`: explicit, idempotent finalization.

PATCH requires `expected_version`, `client_request_id`, and nested `doctor_authored`. Unknown fields fail. Create/update/finalize commands lock authoritative rows. List supports record/consultation status, patient, specialty, action need, dates, exact identifiers or bounded text search, ordering, and pagination.

List payloads exclude complaint, diagnosis, assessment, instructions, and notes. Detail access follows current consultation assignment.

## Compatibility

Legacy `/api/medical-records/{id}/` reads remain for finalized patient records and legacy doctor flows. Doctor Phase C records reject legacy PATCH. Patient confirmation cannot finalize doctor-command records.
