# Patient Permission Matrix

| Resource/action | Patient owner | Other patient | Doctor | Coordinator | Administrator |
|---|---:|---:|---:|---:|---:|
| Own dashboard/profile | Allow | Deny | Deny | Deny | Deny |
| Discover approved doctor | Allow | Allow | Allow | Allow | Allow |
| Create consultation | Allow | Own only | Deny | Deny | Deny |
| Consultation list/detail | Own only | Deny | Assigned scope | Operational scope | Operational scope |
| Cancel consultation | Own + state policy | Deny | Deny | Deny | Deny |
| Intake answer | Own + state policy | Deny | Deny | Deny | Deny |
| Conversation messages | Own consultation | Deny | Assigned scope | Deny | Deny |
| Medical record | Own, read-only | Deny | Assigned workflow | Operational scope | Operational scope |
| Notification read | Recipient only | Deny | Recipient only | Recipient only | Recipient only |
| Privacy export | Subject only | Deny | Deny | Deny | Staff workflow only |
| Deletion request | Subject only | Deny | Deny | Review scope | Review scope |

Rules are enforced by backend querysets/permissions. Frontend route guards are
defense in depth, never authorization. Cross-owner lookups return 404 where
resource existence must not be disclosed. Patient serializers exclude staff,
license, AI, audit, private-contact, and storage fields.

Evidence: Phase A–D backend object-permission suites and
`e2e/phase-f-permissions.spec.ts`.
