# Medical Care Connect (MCC)

**An AI-Assisted Medical Intake and Consultation Platform.**

A modular Django backend that powers a platform connecting patients with healthcare providers through intelligent intake workflows and secure consultations.

## Current Phase

**Phase 1 — Backend Foundation (complete)**

- Django project with split settings (base / development / production)
- Custom user model (UUID PK, email login, role-based)
- Accounts API with health check
- Modular monolith application structure
- PostgreSQL-ready configuration with SQLite development fallback

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
│   ├── accounts/        # Custom user model, API
│   ├── patients/        # Placeholder
│   ├── doctors/         # Placeholder
│   ├── specialties/     # Placeholder
│   ├── consultations/   # Placeholder
│   ├── messaging/       # Placeholder
│   ├── medical_records/ # Placeholder
│   ├── ai_intake/       # Placeholder
│   ├── notifications/   # Placeholder
│   └── audit/           # Placeholder
└── tests/               # Essential tests
```

## API Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/health/` | No | Health check |
| `GET /api/accounts/me/` | Yes | Current user profile |

## Tech Stack

- **Python 3.12+**
- **Django 5.1** with Django REST Framework
- **PostgreSQL** (production) / **SQLite** (development)
- `django-environ` for configuration
- `django-cors-headers` for CORS

## Next Phase

Phase 2 will add JWT authentication, user registration, and login endpoints.
