# Frontend Integration Guide

## Backend URL

Default development: `http://127.0.0.1:8000/api`

## Frontend URL

Default development: `http://localhost:5173`

## CORS Setup

In `.env`:
```
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000
```

Backend accepts requests from these origins, with `Authorization` and `Content-Type` headers.

## Docker Database Startup

```bash
docker compose up -d db
docker compose ps
```

## Seed Command

```bash
python manage.py seed_development_data
python manage.py seed_development_data --reset   # Remove seed records
```

## Development Accounts

| Role          | Email                  | Password        |
|---------------|------------------------|-----------------|
| Administrator | admin@mcc.dev          | Development123! |
| Coordinator   | coordinator@mcc.dev    | Development123! |
| Doctor        | dr.ali@mcc.dev         | Development123! |
| Doctor        | dr.sarah@mcc.dev       | Development123! |
| Doctor        | dr.ahmed@mcc.dev       | Development123! |
| Doctor        | dr.emily@mcc.dev       | Development123! |
| Patient       | john.doe@mcc.dev       | Development123! |
| Patient       | jane.smith@mcc.dev     | Development123! |

## Login Flow

1. POST `/api/auth/login/` with `email` + `password`
2. Store `access` and `refresh` tokens
3. Include `Authorization: Bearer <access>` on all authenticated requests
4. When 401, POST `/api/auth/token/refresh/` with `{"refresh": "..."}`
5. On refresh failure, clear tokens and redirect to `/login`

## Token Refresh Flow

Backend rotates refresh tokens (blacklists old ones). Always use the latest refresh token from the login or refresh response.

## Full Patient Workflow

1. POST `/api/auth/register/patient/` or use seeded `john.doe@mcc.dev`
2. Login → GET `/api/auth/login/`
3. Load dashboard → GET `/api/patients/me/dashboard/`
4. Browse doctors → GET `/api/doctors/` (supports `?page=1&page_size=20`)
5. Create consultation → POST `/api/consultations/` with `doctor_id`, `specialty`, `description`
6. View detail → GET `/api/consultations/<id>/` (includes `actions` flags)
7. Start AI intake → POST `/api/consultations/<id>/intake/start/`
8. Answer questions → POST `/api/intake/sessions/<session_id>/answer/`
9. View medical record → GET `/api/medical-records/<record_id>/`
10. Confirm medical record → POST `/api/medical-records/<record_id>/confirm/`
11. Message doctor → GET/POST `/api/messaging/<consultation_id>/messages/`
12. View notifications → GET `/api/notifications/`
13. Update profile → PATCH `/api/patients/me/`

## Full Doctor Workflow

1. Login as `dr.ali@mcc.dev`
2. Load dashboard → GET `/api/doctors/me/dashboard/`
3. List consultations → GET `/api/consultations/`
4. View consultation → GET `/api/consultations/<id>/`
5. Accept → POST `/api/consultations/<id>/accept/`
6. View intake record → GET `/api/medical-records/<id>/`
7. Send message → POST `/api/messaging/<consultation_id>/messages/`
8. Add internal note → POST `/api/messaging/<consultation_id>/internal-notes/`
9. Update profile → PATCH `/api/doctors/me/`

## Coordinator Workflow

1. Login as `coordinator@mcc.dev`
2. Dashboard → GET `/api/staff/dashboard/`
3. List all consultations → GET `/api/staff/consultations/`
4. Transfer → POST `/api/staff/consultations/<id>/transfer/`
5. Change priority → PATCH `/api/staff/consultations/<id>/priority/`
6. Doctor workload → GET `/api/staff/doctors/workload/`

## Common Integration Errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| CORS error | Origin not in CORS_ALLOWED_ORIGINS | Add frontend URL to .env |
| 401 Unauthorized | Token missing or expired | Check Authorization header, refresh |
| 403 Forbidden | Wrong role for endpoint | Verify user role matches endpoint |
| 404 Not Found | Wrong UUID or missing resource | Check IDs in URL |
| Action flag false | Status doesn't allow action | Check consultation status |
| AI intake fails | DeepSeek not configured | Set AI_INTAKE_ENABLED=false in .env |
| Pagination wrong | Missing `page` param | Add `?page=1&page_size=20` |
