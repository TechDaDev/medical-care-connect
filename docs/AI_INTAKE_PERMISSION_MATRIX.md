# AI Intake Permission Matrix

## Patient intake endpoints

`POST /api/consultations/<id>/intake/start/`
`GET /api/intake/sessions/<id>/`
`POST /api/intake/sessions/<id>/answer/`
`GET /api/intake/sessions/<id>/review/`
`PATCH /api/intake/sessions/<id>/corrections/`
`POST /api/intake/sessions/<id>/confirm/`
`POST /api/intake/sessions/<id>/submit/`

| Actor | Allowed |
| --- | --- |
| Patient who owns the consultation | yes |
| Unrelated patient | no (404) |
| Assigned doctor via patient endpoints | no (403) |
| Unrelated doctor | no |
| Coordinator | no |
| Administrator | no |
| Anonymous | no (401) |

## Doctor intake projection

`GET /api/consultations/<id>/doctor-intake/` (approved assigned doctor only)

| Actor | Allowed |
| --- | --- |
| Approved, assigned doctor | yes |
| Unrelated doctor | no (404) |
| Transferred-away doctor | no |
| Pending doctor | no |
| Suspended doctor | no |
| Patient via doctor endpoint | no |
| Coordinator/administrator via doctor-only endpoint | no |
| Anonymous | no |

Staff endpoints remain separate when they exist.

## Enforcement

- Patient ownership via `consultation__patient__user=request.user`.
- Doctor access via `_doctor_consultation_queryset(request.user)` filtered by
  the assigned doctor.
- `IsAuthenticated`, `IsPatient`, `IsApprovedDoctor` permission classes.
