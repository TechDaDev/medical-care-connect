# Doctor messages

`GET /api/doctors/me/message-threads/` lists only assigned doctor consultations. Approved active doctor required.

Filters: `unread_only`, `patient_awaiting_response`, `consultation_status`, `priority`, `patient`, `specialty`, `search`, `ordering`, `page`, `page_size`. Page size: 20 default, 50 maximum. Default order: patient awaiting response, unread count descending, newest message.

Projection contains safe patient display name, specialty, status, priority, unread count, bounded 160-character preview, availability reason, and doctor-relative action path. Internal notes, contact data, and medical records excluded. Conversation route remains `/app/doctor/messages/:consultationId`; existing assigned-doctor checks and batch read receipts remain authoritative.

Measured SQLite test count: 2 queries for one page, independent of consultation count. Deployment ceiling remains 7 for database/backend variance.
