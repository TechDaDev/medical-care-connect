# Patient Messages and Notifications

## Messages

- Thread overview: `GET /api/patients/me/message-threads/`
- Conversation: `GET/POST /api/messaging/:consultationId/messages/`
- Read receipt: `POST /api/messaging/:consultationId/messages/read/`
- Unread counts: consultation-specific and aggregate messaging endpoints.

Ownership is checked on every request. Payloads expose safe sender identity, not
email or staff-only data. Message creation is idempotent by client request ID.
Read operations exclude messages authored by current patient.

## Notifications

- List: `GET /api/notifications/`
- Mark one/read set/read all: notification mutation endpoints
- Count: `GET /api/notifications/unread-count/`

Only recipient-owned notifications can be read. Mark-all is bounded and
idempotent. Notifications are in-app only; email, SMS, and push delivery are
outside current product architecture.

## Evidence

- Backend: `tests/test_patient_phase_c.py`,
  `tests/test_patient_phase_d.py`
- Frontend: `src/test/patientPhaseC.test.tsx`,
  `src/test/patientPhaseD.test.tsx`
- Browser: `e2e/patient-phase-d.spec.ts`
- Thread overview ceiling: 7 queries.
- Notification list ceiling: 7 queries.
- Mark-all ceiling: 5 queries.
