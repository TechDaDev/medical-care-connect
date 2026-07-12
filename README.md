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

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env if needed (defaults work for local SQLite development)

# Run migrations
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver

# Verify health
curl http://localhost:8000/api/health/
```

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
