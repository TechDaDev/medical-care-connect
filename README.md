# Medical Care Connect (MCC)

**An AI-Assisted Medical Intake and Consultation Platform.**

A modular Django backend that powers a platform connecting patients with healthcare providers through intelligent intake workflows and secure consultations.

## Current Phase

**Phase 2 — Authentication, Profiles & Specialties (complete)**

- JWT authentication (access + refresh tokens) via `djangorestframework-simplejwt`
- Patient registration (auto-creates `User` + `PatientProfile`)
- Role-based permission classes (`IsPatient`, `IsDoctor`, `IsCoordinator`, `IsAdministrator`, etc.)
- Token blacklisting for secure logout
- Specialty management (CRUD via admin; public list/retrieve)
- Patient profiles (date of birth, gender, blood type, emergency contact, language)
- Doctor profiles (specialty, license, qualifications, approval workflow, fee)
- Approval workflow: doctors created through admin, approved by coordinator/administrator

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
│   ├── consultations/   # Placeholder
│   ├── messaging/       # Placeholder
│   ├── medical_records/ # Placeholder
│   ├── ai_intake/       # Placeholder
│   ├── notifications/   # Placeholder
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
| `GET` | `/api/specialties/` | No | List all specialties |
| `GET` | `/api/specialties/<id>/` | No | Retrieve a specialty |
| `POST` | `/api/specialties/` | Yes | Create a specialty |
| `PATCH` | `/api/specialties/<id>/` | Yes | Update a specialty |

## Tech Stack

- **Python 3.12+**
- **Django 5.1** with Django REST Framework
- **PostgreSQL** (production) / **SQLite** (development)
- **JWT authentication** via `djangorestframework-simplejwt`
- `django-environ` for configuration
- `django-cors-headers` for CORS

## Next Phase

Phase 3 will add consultation workflows, patient intake forms, and AI-assisted triage.
