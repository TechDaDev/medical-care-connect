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

---

## Phase 8C: Observability & Operations Variables

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_FORMAT` | `json` | `json` or `simple` |
| `LOG_SERVICE_NAME` | `mcc-backend` | Service identifier |
| `LOG_INCLUDE_REQUESTS` | `true` | Enable request logging |
| `LOG_SLOW_REQUEST_MS` | `1000` | Slow request threshold |
| `LOG_IP_HASH_SALT` | `""` | Salt for IP hashing (required in production) |

### Error Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `ERROR_MONITOR_PROVIDER` | `disabled` | `disabled` or `sentry` |
| `ERROR_MONITOR_DSN` | `""` | Sentry DSN |
| `ERROR_MONITOR_ENVIRONMENT` | `""` | Environment tag |
| `ERROR_MONITOR_RELEASE` | `""` | Release version |

### Backup

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ROOT` | `backups/` | Backup output directory |
| `BACKUP_RETENTION_COUNT` | `7` | Number of backups to keep |

### Data Export

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_EXPORT_ROOT` | `exports/` | Export output directory |
| `DATA_EXPORT_EXPIRY_DAYS` | `7` | Export download expiry |

### Application Version

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_VERSION` | `0.0.0` | Semantic version |
| `APP_RELEASE` | `""` | Release name |
| `GIT_COMMIT_SHA` | `""` | Git commit hash |

### Health / Readiness Paths

| Path | Purpose |
|------|---------|
| `GET /api/health/` | Process alive (no DB) |
| `GET /api/readiness/` | DB + storage check |

Operations (admin-only):
| Path | Purpose |
|------|---------|
| `GET /api/staff/operations/status/` | Detailed operational state |
| `GET /api/staff/operations/metrics/` | Aggregated counts |
