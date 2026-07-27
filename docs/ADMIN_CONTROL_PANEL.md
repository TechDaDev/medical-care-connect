# Administrator Control Panel

## Architecture

React routes under `/app/staff` call `/api/staff/*` through cookie-authenticated API clients. Django views use `CookieJWTAuthentication`, explicit role permissions, service-layer transitions, serializers, and database models. Navigation visibility is convenience only; route guards and backend permissions remain authoritative.

## Feature map

| Area | Frontend route | Backend area |
|---|---|---|
| Dashboard | `/app/staff` | `/api/staff/dashboard/` |
| Doctor applications | `/app/staff/doctor-applications` | `/api/staff/doctors/applications/` |
| Users | `/app/staff/users` | `/api/staff/users/` |
| Privacy requests | `/app/staff/privacy-requests` | `/api/staff/privacy/deletion-requests/` |
| Audit | `/app/staff/audit` | `/api/staff/audit-events/` |
| Specialties | `/app/staff/specialties` | `/api/staff/specialties/` |
| Attachments | `/app/staff/attachments` | `/api/staff/attachments/` |
| Operations | `/app/staff/operations` | `/api/staff/operations/status/` |

Administrator-only areas use nested `RequireRole` guards. Coordinator access is limited to dashboard, consultations, doctor applications/workload, and reviews.

## State machines

- Doctor application: `pending -> approved|rejected`; `approved -> suspended`; `suspended -> approved`.
- User status: active/inactive with self-action and final-administrator protection.
- Privacy deletion: `pending -> approved|rejected`; execution uses separate processing/completed/failed states.
- Attachment: pending/available/quarantined/rejected/deleted. Release requires verified-clean scan state. Retention deletion requires deleted metadata, elapsed retention period, and terminal consultation.
- Specialty: active/inactive. Deactivation blocks active references; historical references remain.

## Data boundaries

License numbers are masked. License and attachment bytes use protected endpoints. Storage keys, private paths, signed URLs, raw audit metadata, medical text, tokens, and credentials are not rendered. Notification support is in-app only; no delivery provider, retry, cancellation, or delivery status exists.
