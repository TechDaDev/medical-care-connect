# Phase F Acceptance Matrix

Status values: `PASS`, `PARTIAL`, `PENDING`, `NOT APPLICABLE`. Update only from recorded runs.

| Group | Backend endpoint | Frontend route | Allowed | Denied | Backend unit | Frontend unit | Playwright | Docker | Production | Cleanup | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A Dashboard | `staff/dashboard/` | `/app/staff` | admin, coordinator | anon, patient, doctor | PASS | PASS | role/API PASS; numeric UI assertion pending | PASS | PENDING | PASS | PARTIAL |
| A Operations | `staff/operations/*` | `/app/staff/operations` | admin | all others | PASS | contract/locale PASS | desktop/mobile PASS | PASS | PENDING | PASS | PARTIAL |
| B Doctor applications | `staff/doctors/applications/*` | `/app/staff/doctor-applications*` | staff | anon, patient, doctor | PASS | contract tests present | list/access PASS; mutation UI pending | PASS | PENDING | PASS | PARTIAL |
| C Users/roles | `staff/users/*` | `/app/staff/users*` | admin | all others | PASS | contract tests present | permission PASS; mutation UI pending | PASS | PENDING | PASS | PARTIAL |
| D Privacy | `staff/privacy/deletion-requests/*` | `/app/staff/privacy-requests*` | admin | all others | PASS | contract tests present | patient flow/permission PASS; admin mutation UI pending | PASS | PENDING | PASS | PARTIAL |
| E Audit/CSV | `staff/audit-events/*` | `/app/staff/audit*` | admin | all others | PASS | contract tests present | permission PASS; CSV UI pending | PASS | PENDING | PASS | PARTIAL |
| F Specialties | `staff/specialties/*` | `/app/staff/specialties*` | admin | all others | PASS | PASS | permission PASS; mutation UI pending | PASS | PENDING | PASS | PARTIAL |
| G Attachments | `staff/attachments/*` | `/app/staff/attachments*` | admin | all others | PASS | PASS | participant flow/permission PASS; admin mutation UI pending | PASS | PENDING | PASS | PARTIAL |
| H Localization | n/a | all staff routes | authenticated role | n/a | NOT APPLICABLE | locale parity PASS | desktop RTL PASS; mobile RTL pending | n/a | PENDING | n/a | PARTIAL |
| I Auth/CSRF | `auth/*` | `/login`, protected routes | role dependent | role dependent | PASS | PASS | normal login/logout PASS | PASS | PENDING | PASS | PARTIAL |
| J Deployment | health/readiness | landing/login/admin chunks | n/a | n/a | PASS | build PASS | 60/60 local PASS | PASS | PENDING | n/a | PARTIAL |

Measured frontend statement coverage is 15.21%; no arbitrary threshold is enforced. Phase F must not be called complete while `PARTIAL` or `PENDING` entries remain.
