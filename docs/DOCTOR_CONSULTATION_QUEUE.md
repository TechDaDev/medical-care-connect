# Doctor Consultation Queue

Doctor Phase B queue uses `GET /api/consultations/doctor/`. Access requires authenticated, active, approved doctor. Query scope always uses authenticated doctor's profile; caller cannot expand assignment scope.

Response uses page-number pagination. Default page size: 20. Maximum: 50. Safe rows include consultation ID/status/priority/timestamps, patient display name plus coarse age group/gender, localized specialty, unread count, action signal/type, intake-ready flag, record-exists flag, attachment count, and server-authoritative available actions. Rows exclude complaint description, cancellation reason, message/note content, emails, intake answers, AI internals, and storage identifiers.

Filters: `status`, `status_group`, `priority`, `patient`, `specialty`, `needs_doctor_action`, `has_unread_messages`, `has_completed_intake`, `has_medical_record`, `created_after`, `created_before`, and safe `search`. Groups: `new_requests`, `needs_action`, `active`, `awaiting_patient`, `completed`, `cancelled`, `terminal`. Search covers consultation UUID, patient name, and localized specialty names only.

Ordering allowlist: `created_at`, `updated_at`, `submitted_at`, `priority`, and descending variants. Default ranks emergencies, urgent work, action-needed states, unread work, then recent updates.

Queryset preloads patient, doctor, specialty, intake, and record; aggregates messages, attachments, and notes. Page size does not cause serializer queries.

Frontend route: `/app/doctor/consultations`. Filters stay in URL. Desktop table and mobile cards consume same safe contract.
