# Deployment

## Prerequisites

- Docker and Docker Compose
- PostgreSQL 16 (production)

## Quick Start

```bash
# Build and start
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Run migrations
docker compose -f docker-compose.production.yml exec backend \
    python manage.py migrate --noinput
```

## Environment

Copy `.env.production.example` to `.env` and fill in:

```bash
cp .env.production.example .env
# Edit .env with production values
```

Required variables:
- `SECRET_KEY` — long random string
- `ALLOWED_HOSTS` — comma-separated domains
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `CORS_ALLOWED_ORIGINS` — frontend URL
- `CSRF_TRUSTED_ORIGINS` — frontend URL

## Docker Build

```bash
docker build -t mcc-backend:latest .
```

## Health Checks

| Endpoint | Purpose |
|----------|---------|
| GET `/api/health/` | App alive |
| GET `/api/readiness/` | DB + AI status |

## Migrations

Auto-run at container start when `RUN_MIGRATIONS=true`.

Manual: `docker compose exec backend python manage.py migrate --noinput`

## Static Files

Collected at container start via entrypoint.sh.

Manual: `python manage.py collectstatic --noinput`

## Compose

```bash
docker compose -f docker-compose.production.yml config  # validate
docker compose -f docker-compose.production.yml up -d    # start
docker compose -f docker-compose.production.yml down     # stop
```

## Rollback

```bash
# Revert to previous image tag
docker compose -f docker-compose.production.yml stop backend
docker compose -f docker-compose.production.yml rm backend
# Re-tag previous image
docker tag mcc-backend:previous mcc-backend:latest
docker compose -f docker-compose.production.yml up -d backend
# Roll back DB if needed
docker compose exec db psql -U mcc_user -d mcc_production -f /backups/rollback.sql
```

## Notes

- No JWT stored in localStorage
- No `.env` committed
- No SQLite in production
- Static files served via WhiteNoise (Django)
- Gunicorn with 4 sync workers (configurable)
