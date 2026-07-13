# Railway Deployment

## Overview

Deploy MCC to Railway.app. Three services are required: backend, frontend,
and PostgreSQL.

## Prerequisites

- Railway account with billing enabled
- `railway` CLI installed
- Git repo connected to Railway

## Services

### PostgreSQL

Provision via Railway's PostgreSQL plugin.

- Railway provides `DATABASE_URL` (PostgreSQL connection string)
- Parse into `POSTGRES_*` env vars if using individual settings
- Or configure Django to read `DATABASE_URL` directly

### Backend Service

| Setting | Value |
|---------|-------|
| Root directory | `mcc_backend/` |
| Start command | `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --timeout 120` |
| Health check path | `/api/health/` |
| Readiness path | `/api/readiness/` |

### Frontend Service

| Setting | Value |
|---------|-------|
| Root directory | `mcc_frontend/` |
| Build command | `npm run build` |
| Start command | `nginx -g 'daemon off;'` (Dockerfile-based) |
| Health check | `/healthz` (returns 200 from nginx) |

## Backend Environment Variables

```bash
# Django
SECRET_KEY=<long-random-string>
DEBUG=False
ALLOWED_HOSTS=<backend-railway-url>,<custom-domain>
CORS_ALLOWED_ORIGINS=<frontend-railway-url>,<custom-domain>
CSRF_TRUSTED_ORIGINS=<frontend-railway-url>,<custom-domain>

# PostgreSQL — Railway provides DATABASE_URL, parse accordingly
DATABASE_URL=postgresql://...
# Or individual:
POSTGRES_DB=railway
POSTGRES_USER=railway
POSTGRES_PASSWORD=...
POSTGRES_HOST=...
POSTGRES_PORT=5432
DATABASE_SSL_REQUIRE=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_SERVICE_NAME=mcc-backend
LOG_INCLUDE_REQUESTS=true
LOG_IP_HASH_SALT=<long-random-string>

# Error monitoring (disabled by default)
ERROR_MONITOR_PROVIDER=disabled

# Backups
BACKUP_ROOT=/app/backups
BACKUP_RETENTION_COUNT=7

# DeepSeek (optional)
AI_INTAKE_ENABLED=false
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# Version
APP_VERSION=0.0.0
APP_RELEASE=
GIT_COMMIT_SHA=
```

## Frontend Environment Variables

```bash
VITE_API_BASE_URL=https://<backend-railway-url>/api
VITE_APP_NAME=Medical Care Connect
VITE_APP_VERSION=0.0.0
VITE_APP_RELEASE=
VITE_MESSAGE_POLL_INTERVAL_MS=10000
VITE_NOTIFICATION_POLL_INTERVAL_MS=30000
```

## Cookie Configuration

In production, cookie settings **must** include:

```python
# Already in production settings:
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
```

Required for:
- Cookies sent only over HTTPS (Secure flag)
- Cross-origin requests from frontend domain
- CSRF protection

## Health Checks

Railway uses:
- **Backend:** `GET /api/health/` returns `{"status": "healthy"}`
- **Frontend:** nginx `/healthz` returns 200

Configure Railway health check paths accordingly.

## Railway Bucket (Future Work)

S3-compatible object storage is available on paid Railway plans. Currently
the attachment system uses `LocalProtectedStorageBackend`. To enable:

1. Provision a Railway Bucket
2. Set env vars:
   ```
   RAILWAY_BUCKET_ENDPOINT=
   RAILWAY_BUCKET_NAME=
   RAILWAY_BUCKET_ACCESS_KEY=
   RAILWAY_BUCKET_SECRET_KEY=
   RAILWAY_BUCKET_REGION=
   ATTACHMENT_STORAGE_BACKEND=railway
   ```
3. Create the `RailwayBucketStorageBackend` adapter
4. Migrate files using the storage migration skeleton

## Security

- Never commit `.env` to repository
- Use Railway's built-in environment variable management
- Enable `DATABASE_SSL_REQUIRE=true`
- Set `LOG_IP_HASH_SALT` to a long random string
- Keep `SECRET_KEY` rotated
