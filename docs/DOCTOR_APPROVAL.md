# Doctor approval

New doctors start `pending`, unapproved, non-public, and not accepting consultations.

## Pending doctor restrictions

| Operation | Access |
|---|---|
| View own profile (GET /doctors/me/) | ✅ |
| Update own profile (PATCH /doctors/me/) | ✅ |
| View own pending-approval page | ✅ |
| View doctor dashboard | ❌ (403 — IsApprovedDoctor) |
| List/create availability | ❌ (403 — IsApprovedDoctor) |
| Update/delete availability | ❌ (403 — IsApprovedDoctor) |
| Toggle accepting consultations | ❌ (403 — IsApprovedDoctor) |
| Accept consultations | ❌ |
| Appear in public doctor directory | ❌ (filtered by is_approved) |

Pending doctors **can** log out.

## Staff review workflow

Only `coordinator` or `administrator` roles.

1. `GET /api/staff/doctors/applications/?status=pending` — list pending
2. `POST /api/staff/doctors/applications/<id>/review/` — approve/reject/suspend

### Review request

```json
{"action": "approve", "reason": "Credentials verified."}
```

### Review response

```json
{"id": "<uuid>", "approval_status": "approved"}
```

### Actions

| Action | Effect |
|---|---|
| `approve` | Sets `is_approved=true`, `approval_status=approved`, `is_accepting_consultations=false` — doctor must explicitly enable |
| `reject` | Sets `approval_status=rejected`, `is_approved=false`, `is_accepting_consultations=false` |
| `suspend` | Sets `approval_status=suspended`, `is_approved=false`, `is_accepting_consultations=false` |

## Security

| Control | Implementation |
|---|---|
| Unauthorized approval | ❌ 403 — `IsCoordinatorOrAdministrator` |
| Patient reviewing doctor | ❌ 403 |
| Doctor self-approval | ❌ (no endpoint) |
| License in review response | ✅ (staff-only field) |
| License in public directory | ❌ (not in PublicDoctorListSerializer/DetailSerializer) |
| Review note in public responses | ❌ (stored as `approval_note`, not exposed) |
| Notification on approval | ✅ `DOCTOR_APPLICATION_STATUS` notification to doctor |
| Audit event | ✅ `security.doctor.application.reviewed` |

## Test coverage

- 4 dedicated approval tests in test_doctor_registration.py
- Approval, rejection, unauthorized denial, notification verified
- Privacy of license number verified in public context
