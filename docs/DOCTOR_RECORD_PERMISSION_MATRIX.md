# Doctor record permission matrix

| Actor/state | List/detail | Create/update/finalize | Outcome |
|---|---:|---:|---:|
| Assigned approved active doctor | Allow | Allow per record/consultation state | Allow per backend action policy |
| Unrelated doctor | Deny | Deny | Deny |
| Previous doctor after transfer | Deny | Deny | Deny |
| Pending/rejected/suspended/inactive doctor | Deny | Deny | Deny |
| Patient | Finalized patient-safe projection only | Deny | Deny |
| Coordinator/administrator via doctor endpoint | Deny | Deny | Deny |
| Anonymous | Deny | Deny | Deny |

Doctor access is resolved from current consultation assignment on every request. Transfer locks consultation and record, writes outcome, then changes assignment atomically.
