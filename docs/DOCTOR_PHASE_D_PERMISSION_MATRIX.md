# Doctor Phase D permission matrix

| Surface | Approved active assigned/owner doctor | Other doctor | Pending/rejected/suspended/inactive doctor | Patient/coordinator/admin/anonymous |
|---|---:|---:|---:|---:|
| Message overview | Allow | Own rows only | Deny | Deny |
| Conversation | Assigned only | Deny | Deny | Doctor route deny |
| Notifications | Own recipient only | Deny | Deny | Deny |
| Reviews/response | Own consultation only | Deny | Deny | Deny |
| Own profile | Allow by existing capability policy | Deny | Existing access-state policy | Deny |
| Privacy/export/deletion | Own account only | Deny | Deny | Deny |

Backend permissions and ownership queries are authoritative. Frontend role gates are navigation only.
