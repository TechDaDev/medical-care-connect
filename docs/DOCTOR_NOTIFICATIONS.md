# Doctor notifications

Endpoints:

- `GET /api/doctors/me/notifications/`
- `POST /api/doctors/me/notifications/:id/read/`
- `POST /api/doctors/me/notifications/read-all/`

List supports pagination, unread/type/date filters, ordering, and unread total. Mutations scope by current recipient; one-read is idempotent; read-all is one batch update.

Links are generated from an allowlist of doctor-relative consultation, message, medical-record, review, profile, and privacy paths. External, protocol-relative, patient, staff, and arbitrary stored paths never enter response. Notifications are in-app only. No email, SMS, push, provider, retry, sent, or delivery state exists.
