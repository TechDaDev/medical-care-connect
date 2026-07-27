# Administrator Permission Matrix

`401` means unauthenticated. `403` means authenticated but forbidden. Frontend denial redirects user to own dashboard.

| Area | Anonymous | Patient | Doctor | Coordinator | Administrator |
|---|---:|---:|---:|---:|---:|
| Staff dashboard | 401 | 403 | 403 | 200 | 200 |
| Staff consultations | 401 | 403 | 403 | 200 | 200 |
| Reviews moderation | 401 | 403 | 403 | 200 | 200 |
| Doctor workload | 401 | 403 | 403 | 200 | 200 |
| Doctor applications | 401 | 403 | 403 | 200 | 200 |
| Users and roles | 401 | 403 | 403 | 403 | 200 |
| Privacy administration | 401 | 403 | 403 | 403 | 200 |
| Audit and CSV | 401 | 403 | 403 | 403 | 200 |
| Specialty administration | 401 | 403 | 403 | 403 | 200 |
| Attachment administration | 401 | 403 | 403 | 403 | 200 |
| Operations | 401 | 403 | 403 | 403 | 200 |

Mutations also require CSRF. Sensitive writes require transition validation; user, privacy, specialty, attachment, and doctor-application changes have concurrency or state checks. Navigation hiding never grants or denies API access.
