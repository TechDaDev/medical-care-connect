# Doctor access states

`GET /api/doctors/me/access-state/` is sole doctor SPA routing authority.

| State | Dashboard | Availability | Profile edit | Next path |
|---|---:|---:|---:|---|
| `approved` | yes | yes | yes | `/app/doctor` |
| `pending` | no | no | yes | `/app/doctor/pending-approval` |
| `rejected` | no | no | yes | `/app/doctor/application-rejected` |
| `suspended` | no | no | no | `/app/doctor/suspended` |
| `missing_profile` | no | no | no | `/app/doctor/profile-missing` |
| `inactive` | no | no | no | `/login` |

Contract exposes capability flags, stable reason code, approval state, safe profile
identifier/timestamps, accepting state, and next route. It excludes license data,
approval notes, reviewer identity, suspension metadata, and audit details.

Operational permission requires active doctor user plus both
`approval_status=approved` and `is_approved=true`. Frontend gates improve
navigation; backend permissions remain authoritative.
