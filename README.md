# Medical Care Connect (MCC)

**An AI-Assisted Medical Intake and Consultation Platform.**

A modular Django backend that powers a platform connecting patients with healthcare providers through intelligent intake workflows and secure consultations.

## Current Phase

**Phase 11 — Reviews, Reputation, Moderation & Trust (complete)**

- Patient reviews for completed consultations (1–5★ ratings)
- 72-hour editable review window with withdrawal support
- Anonymous review option with identity privacy guarantees
- Doctor public reputation: average rating, distribution, response rate, trend
- Doctor responses to reviews (one per review)
- Review reporting with 6 reason categories
- Staff moderation: hide, remove, restore, manage reports
- Notification events for all review workflows
- Trilingual interface (English, Arabic, Kurdish Sorani)

## Requirements

- Python 3.12+
- pip
- Docker + Docker Compose (for PostgreSQL)

## Quick Start (with Docker PostgreSQL)

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env POSTGRES_PASSWORD if desired (default works for local dev)

# Start PostgreSQL in Docker
docker compose up -d db

# Verify PostgreSQL is running
docker compose ps
docker compose logs db

# Run migrations on PostgreSQL
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver

# Verify health
curl http://localhost:8000/api/health/
```

## Docker Commands

| Command | Action |
|---------|--------|
| `docker compose up -d db` | Start PostgreSQL in background |
| `docker compose ps` | Check container status |
| `docker compose logs db` | View PostgreSQL logs |
| `docker compose stop` | Stop PostgreSQL (data preserved) |
| `docker compose down` | Stop and remove container (data preserved) |
| `docker compose down -v` | Stop and remove container + volume (data lost) |

### Architecture

- **Django** runs locally on your machine.
- **PostgreSQL** runs inside a Docker container.
- `POSTGRES_HOST=localhost` because Django connects to the local Docker host.
- Database data persists in the named Docker volume `postgres_data`.

### Development without Docker

If Docker is unavailable, Django falls back to SQLite automatically — just leave `POSTGRES_DB` commented out or empty in `.env`.

## Project Structure

```
mcc_backend/
├── config/              # Django project configuration
│   ├── settings/
│   │   ├── base.py      # Shared settings
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── core/            # BaseModel abstract class
│   ├── accounts/        # Custom user model, JWT auth, permissions
│   ├── patients/        # Patient profiles
│   ├── doctors/         # Doctor profiles
│   ├── specialties/     # Medical specialties
│   ├── consultations/   # Consultation requests
│   ├── messaging/       # Patient-doctor messages + internal notes
│   ├── medical_records/ # Medical record drafts
│   ├── ai_intake/       # AI-assisted intake (DeepSeek)
│   ├── notifications/   # In-app notifications
│   └── audit/           # Placeholder
└── tests/               # Unit & integration tests
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/health/` | No | Health check |
| `POST` | `/api/auth/register/patient/` | No | Register patient (auto-creates profile) |
| `POST` | `/api/auth/login/` | No | Log in (returns JWT tokens + user) |
| `POST` | `/api/auth/token/refresh/` | No | Refresh access token |
| `POST` | `/api/auth/logout/` | Yes (JWT) | Log out (blacklists refresh token) |
| `GET` / `PATCH` | `/api/accounts/me/` | Yes (JWT) | Get/update current user profile |
| `GET` / `PATCH` | `/api/patients/me/` | Yes (Patient) | Get/update own patient profile |
| `GET` / `PATCH` | `/api/doctors/me/` | Yes (Doctor) | Get/update own doctor profile |
| `GET` / `POST` | `/api/doctors/me/availability/` | Yes (Doctor) | List/create own availability slots |
| `PATCH` / `DELETE` | `/api/doctors/me/availability/<id>/` | Yes (Doctor) | Update/delete a slot |
| `PATCH` | `/api/doctors/me/availability-status/` | Yes (Doctor/Admin) | Toggle accepting consultations |
| `GET` | `/api/doctors/` | No | List approved doctors (public directory) |
| `GET` | `/api/doctors/<id>/` | No | Doctor public profile |
| `GET` | `/api/specialties/` | No | List all specialties |
| `GET` | `/api/specialties/<id>/` | No | Retrieve a specialty |
| `POST` | `/api/specialties/` | Yes | Create a specialty |
| `PATCH` | `/api/specialties/<id>/` | Yes | Update a specialty |
| `GET`, `POST` | `/api/consultations/` | Yes | List (role-scoped) / Create (Patient) consultation |
| `GET` | `/api/consultations/<id>/` | Yes | Consultation detail |
| `POST` | `/api/consultations/<id>/accept/` | Yes (Doctor) | Accept consultation |
| `POST` | `/api/consultations/<id>/cancel/` | Yes | Cancel consultation (requires reason) |
| `POST` | `/api/consultations/<id>/intake/start/` | Yes (Patient) | Start AI-assisted medical intake |
| `POST` | `/api/intake/sessions/<id>/answer/` | Yes (Patient) | Submit answer during intake |
| `GET` | `/api/intake/sessions/<id>/` | Yes | Retrieve intake session + messages |
| `GET` | `/api/medical-records/<id>/` | Yes | Retrieve medical record draft |
| `PATCH` | `/api/medical-records/<id>/` | Yes (Doctor) | Update draft record |
| `POST` | `/api/medical-records/<id>/confirm/` | Yes (Patient) | Confirm finalized record |
| `GET`, `POST` | `/api/messaging/<consultation_id>/messages/` | Yes | List (auto-mark read) / send consultation messages |
| `POST` | `/api/messaging/<consultation_id>/messages/read/` | Yes | Mark specific messages as read |
| `GET` | `/api/messaging/<consultation_id>/messages/unread-count/` | Yes | Unread count for a consultation |
| `GET` | `/api/messaging/unread-counts/` | Yes | Unread counts for all user consultations |
| `GET`, `POST` | `/api/messaging/<consultation_id>/internal-notes/` | Yes (Doctor) | List / create doctor internal notes |
| `GET`, `DELETE` | `/api/messaging/<consultation_id>/internal-notes/<id>/` | Yes (Doctor) | Get / delete an internal note |
| `GET` | `/api/notifications/` | Yes | List notifications (`?unread=true`) |
| `POST` | `/api/notifications/read/` | Yes | Mark all notifications as read |
| `GET` | `/api/notifications/unread-count/` | Yes | Unread notification count |

## Phase 4 — AI-Assisted Medical Intake

Phase 4 adds an AI-powered medical intake workflow that collects structured patient information before a consultation. The system uses DeepSeek (OpenAI-compatible) for conversational intake and deterministic keyword screening for emergencies.

### Scope

- **AI does not diagnose.** The system collects patient-reported symptoms and history for the doctor's review.
- **AI does not prescribe.** No medication or treatment recommendations are generated.
- **MCC is not an emergency service.** The system includes keyword-based emergency screening. If an emergency is detected, the patient is advised to seek immediate emergency care.
- **Messaging is not implemented.** The consultation lifecycle and intake are separate from direct patient–doctor messaging (planned for a future phase).

### AI Intake Behavior

| Condition | Response |
|-----------|----------|
| AI enabled (default) | Conversational intake via DeepSeek |
| AI disabled (`AI_INTAKE_ENABLED=false`) | Start returns HTTP 503 |
| Emergency keywords detected | Session stops, deterministic screen, no AI call |

### Emergency Screening

Before every AI call, the system runs deterministic keyword screening for:
- Self-harm / suicide
- Severe chest pain / cardiac
- Difficulty breathing
- Severe bleeding
- Stroke symptoms
- Anaphylaxis

If triggered, the session enters `emergency_stopped` status and returns an emergency message. No AI call is made.

### DeepSeek Environment Variables

These are managed in `.env`:

```
DEEPSEEK_API_KEY=           # API key (required if AI enabled)
DEEPSEEK_BASE_URL=https://api.deepseek.com  # API endpoint
DEEPSEEK_MODEL=             # Model name (required if AI enabled)
DEEPSEEK_TIMEOUT_SECONDS=45
DEEPSEEK_MAX_TOKENS=1200
DEEPSEEK_TEMPERATURE=0.2
AI_INTAKE_ENABLED=false     # Master toggle
AI_INTAKE_PROVIDER=deepseek # Provider selection
```

## Phase 8C — Observability, Privacy & Operations

Phase 8C adds production-grade observability, privacy workflows, backup/
restore tooling, and operational endpoints.

### Features

- **Structured JSON logging** — every request logged with correlation ID,
  safe fields only, no PII in logs
- **Request correlation IDs** — `X-Request-ID` header on every response,
  included in error payloads
- **Security event logging** — 18+ typed security events (auth, CSRF,
  attachments, consultations, accounts, data exports)
- **Error monitoring interface** — `ErrorMonitor` ABC with disabled default,
  Sentry reserved
- **IP hashing** — one-way salted SHA-256, configured via `LOG_IP_HASH_SALT`
- **Backup commands** — `backup_database` (pg_dump), `backup_attachments`,
  `verify_backup`, `restore_backup` (verification only), `prune_backups`
- **Disaster recovery test procedure** — documented temp-DB-based DR test
- **Data export** — `DataExportRequest` model with full lifecycle
  (request → process → download → expire)
- **Account deactivation/reactivation** — user self-service, admin override
- **Account deletion requests** — `AccountDeletionRequest` with staff review
  (approve/reject)
- **Anonymizer** — `PreviewOnlyAnonymizer` reports affected records without
  mutation
- **Operations endpoints** — `/api/health/`, `/api/readiness/`,
  `/api/staff/operations/status/`, `/api/staff/operations/metrics/`
- **Runbooks** — 9 runbooks covering backup, restore, outage, deployment
  failure, auth incidents, storage corruption, secret rotation, and account
  deletion review
- **Privacy documentation** — export contents, exclusions, retention policy,
  legal blocks
- **Railway deployment guide** — env vars, health checks, cookie config,
  Railway Bucket future work
- **CI/CD documentation** — backend-ci, e2e-ci, security-ci workflows

## Tech Stack

- **Python 3.12+**
- **Django 5.1** with Django REST Framework
- **PostgreSQL** (production) / **SQLite** (development)
- **JWT authentication** via `djangorestframework-simplejwt`
- `django-environ` for configuration
- `django-cors-headers` for CORS

## Phase 5 — Messaging & Notifications

Phase 5 adds patient-doctor messaging, doctor internal notes, read receipts, and in-app notifications. Statuses expanded with `INTAKE_COMPLETED`, `DOCTOR_REVIEW`, `PHYSICAL_VISIT_REQUIRED`, and `TRANSFERRED`.

### Messaging Rules

| Status | Messaging allowed? |
|--------|:---:|
| submitted, accepted, intake_in_progress, intake_completed, doctor_review, awaiting_patient/doctor, under_review, follow_up_required, physical_visit_required, transferred | ✅ |
| completed, cancelled, emergency_escalated | ❌ |

### Notification Events

| Event | Recipient | When |
|-------|-----------|------|
| Consultation accepted | Patient | Doctor accepts |
| Consultation cancelled | Both participants | Either cancels |
| New message | Non-sender participant | Message sent |
| Intake completed* | Doctor | Intake finishes |
| Record confirmed | Doctor | Patient confirms |
| Record revision requested | Doctor | Patient declines |
