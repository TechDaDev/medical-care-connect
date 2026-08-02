# Doctor Final Permission Matrix

Backend permissions remain authoritative. Client guards improve navigation only.

| Principal/state | Access-state/profile | Approved doctor workspace | Other doctor's objects | Staff workspace |
| --- | --- | --- | --- | --- |
| Approved doctor | Own | Allow | Conceal with 404 | Deny |
| Pending doctor | Own state/profile | Deny 403 | Deny | Deny |
| Rejected doctor | Own state/profile | Deny 403 | Deny | Deny |
| Suspended doctor | Own state/profile | Deny 403 | Deny | Deny |
| Doctor missing profile | Own state | Deny 403 | Deny | Deny |
| Unrelated approved doctor | Own | Own assigned data only | Conceal with 404 | Deny |
| Transfer source doctor | Own | No post-transfer ownership | Conceal with 404 | Deny |
| Transfer target doctor | Own | Assigned transferred data | Allow assigned object | Deny |
| Patient | Patient surfaces | Deny 403 | Deny | Deny |
| Coordinator | Staff surfaces | Deny 403 | Deny | Allow scoped staff access |
| Administrator | Staff surfaces | Deny 403 | Deny | Allow administrator access |
| Anonymous | Public only | Deny 401 | Deny 401 | Deny 401 |

Mutation protections: CSRF for cookie-authenticated writes, expected-state checks, ownership filters, atomic transactions, idempotency keys, and immutable action ledgers where applicable.
