# Patient API Reference

All paths use `/api` prefix. Browser mutations require centralized CSRF
bootstrap and `X-CSRFToken`. Authentication uses HttpOnly `mcc_access` and
`mcc_refresh` cookies; tokens are not returned in JSON.

| Method | Path | Purpose |
|---|---|---|
| GET/PATCH | `/patients/me/` | Read/update own profile |
| GET | `/patients/me/dashboard/` | Dashboard aggregate |
| GET | `/patients/me/medical-records/` | Record list |
| GET | `/patients/me/medical-records/:id/` | Safe record detail |
| GET | `/patients/me/message-threads/` | Message overview |
| GET/POST | `/consultations/` | List/create |
| GET | `/consultations/:id/` | Detail/timeline/actions |
| POST | `/consultations/:id/cancel/` | Cancel with expected status |
| POST | `/consultations/:id/intake/start/` | Start allowed intake |
| GET/POST | `/messaging/:id/messages/` | Conversation/send |
| POST | `/messaging/:id/messages/read/` | Mark incoming read |
| GET | `/notifications/` | Notification list |
| POST | `/notifications/:id/read/` | Mark one read |
| POST | `/notifications/read-all/` | Mark all owned read |
| GET | `/notifications/unread-count/` | Unread count |
| GET/POST | `/privacy/exports/` | Export list/create |
| GET | `/privacy/exports/:id/` | Export state |
| GET | `/privacy/exports/:id/download/` | Private archive |
| GET/POST | `/privacy/deletion-requests/` | List/create |
| GET/DELETE | `/privacy/deletion-requests/:id/` | Detail/cancel |

Error envelope uses `detail`, stable `code`, optional field errors, and optional
request ID. Expected authorization/not-found/validation/conflict/throttle errors
do not expose stack traces.
