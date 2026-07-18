# Account registration

Public users may self-register only as `patient` or `doctor`.

## Endpoints

- `POST /api/auth/register/patient/` — creates patient User + PatientProfile. Role: `patient`.
- `POST /api/auth/register/doctor/` — creates doctor User + pending DoctorProfile. Role: `doctor`.
- Role is assigned server-side. Client-supplied role is ignored.
- Doctor applications authenticate immediately via JWT cookies, return `next_path: /app/doctor/pending-approval`.

## Doctor application fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `specialty` | UUID | Yes | Must reference active Specialty |
| `medical_license_number` | string | Yes | Case-insensitive unique |
| `years_of_experience` | int (0–70) | Yes | |
| `workplace_name` | string | Yes | |
| `professional_bio` | string (max 2000) | Yes | |
| `languages` | [string] | Yes | Values: `ar`, `en`, `ckb` |
| `consultation_fee` | decimal | No | |
| `education` | string | No | |
| `certifications` | string | No | |

## Security

- `coordinator`/`administrator` roles cannot be self-assigned via public registration.
- `POST /api/auth/register/patient/` cannot create coordinator/admin users.
- `RegisterDoctorSerializer` always sets `role=UserRole.DOCTOR` server-side.
- `RegisterPatientSerializer` always sets `role=UserRole.PATIENT` server-side.
- License number uniqueness enforced case-insensitively via DB constraint.
- Duplicate email returns 400.
- Password mismatch returns 400.
- Profile creation failure rolls back user creation (transaction.atomic).
- Staff is notified via DOCTOR_APPLICATION notification.
- Audit event `security.doctor.application.created` is logged.

## Test coverage

- 24 backend tests cover all registration scenarios (tests/test_doctor_registration.py).
- 10 frontend tests cover account-type selection, endpoints, locale keys, and validation.
- Playwright e2e/registration.spec.ts covers full UI flow.
