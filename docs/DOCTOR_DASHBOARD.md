# Doctor dashboard

`GET /api/doctors/me/dashboard/` returns:

- access and safe profile/completeness summaries;
- all consultation lifecycle counts;
- server-authored attention queue;
- five recent consultations;
- five recent unread message threads without message bodies;
- five in-app notifications;
- published-review aggregate and three recent reviews;
- recurring availability summary;
- generation timestamp.

Attention types cover new consultations, completed intake, awaiting-doctor
responses, urgent work, emergency escalation, unread patient messages, and
published reviews awaiting response. Awaiting-patient consultations are not
doctor attention. Action paths are server-created relative SPA paths.

Unread messages use one grouped query over messages and read receipts. No loop
calls per-consultation unread service. Dashboard regression ceiling: 10 queries,
fixed as consultation count grows. Response excludes consultation description,
intake answers, message content, sender email, internal notes, and medical
record narrative.

Notifications remain in-app only. Delivery/provider tracking is absent.
