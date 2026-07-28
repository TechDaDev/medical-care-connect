# Doctor Phase A permission matrix

| Operation | Approved doctor | Pending/rejected doctor | Suspended doctor | Patient | Staff | Anonymous |
|---|---:|---:|---:|---:|---:|---:|
| Access state | yes | yes | yes | no | no | no |
| Own profile read/edit | yes | yes | API policy unchanged | no | no | no |
| Dashboard | yes | no | no | no | no | no |
| Availability list/create | yes | no | no | no | no | no |
| Own slot update/delete | yes | no | no | no | no | no |
| Other doctor's slot | hidden 404 | no | no | no | no | no |
| Accepting-status update | yes | no | no | no | no | no |

Inactive users are rejected by authentication/operational permission. Staff
approval endpoints retain their separate permissions. Object lookups always
scope slot identifier to authenticated doctor profile.
