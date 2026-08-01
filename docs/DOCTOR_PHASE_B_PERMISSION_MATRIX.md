# Doctor Phase B Permission Matrix

| Capability | Assigned approved doctor | Unrelated doctor | Pending/inactive doctor | Patient | Staff |
|---|---:|---:|---:|---:|---:|
| Doctor queue | own only | own only | deny | deny | deny |
| Doctor detail/intake | allow | deny | deny | deny | deny |
| Accept/transition | policy | deny | deny | deny | deny |
| Message | active-state policy | deny | deny | participant policy | staff existing policy |
| Internal notes | allow | deny | deny | deny | deny |
| Attachment list/download | server action policy | deny | deny | participant policy | existing staff policy |
| Attachment upload/delete | active-state server policy | deny | deny | existing patient policy | existing staff policy |
| Medical-record doctor route | unavailable | unavailable | unavailable | existing patient routes | existing staff routes |

Frontend flags are presentation only. Every endpoint independently enforces authentication, approval, assignment, state, and resource policy.
