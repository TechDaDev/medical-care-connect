# Operations Endpoints

## Health

Public endpoint — no authentication required.

```http
GET /api/health/
```

**Purpose:** Simple process-alive check. No database query. Used by load
balancers and orchestrators (Railway, Docker health checks).

**Response 200:**
```json
{
  "status": "healthy"
}
```

## Readiness

Public endpoint — no authentication required.

```http
GET /api/readiness/
```

**Purpose:** Verifies the application can serve traffic by checking critical
dependencies. Used by orchestrators for rolling updates.

**Checks:**
- Database connectivity (`SELECT 1`)
- Attachment storage backend writable

**Response 200:**
```json
{
  "status": "ready",
  "database": true,
  "attachment_storage": true
}
```

**Response 503:**
```json
{
  "status": "unhealthy",
  "database": false,
  "attachment_storage": true
}
```

## Operations Status

**Admin only.** Requires `CookieJWTAuthentication` + `IsAdministrator`.

```http
GET /api/staff/operations/status/
```

**Purpose:** Provides a detailed snapshot of the application's operational
state for administrators.

**Response:**
```json
{
  "version": "0.0.0",
  "release": "",
  "commit": "abc12345",
  "environment": "production",
  "database_available": true,
  "attachment_backend_provider": "local",
  "attachment_root_writable": true,
  "attachment_scan_mode": "disabled",
  "ai_enabled": false,
  "error_monitor_provider": "disabled",
  "latest_migration": "001_initial",
  "retention_candidates": 0,
  "degraded_components": []
}
```

| Field | Description |
|-------|-------------|
| `version` | `APP_VERSION` env var |
| `release` | `APP_RELEASE` env var |
| `commit` | First 8 chars of `GIT_COMMIT_SHA` |
| `environment` | `production` or `development` |
| `database_available` | Can execute `SELECT 1` |
| `attachment_backend_provider` | Storage backend class name |
| `attachment_root_writable` | Storage root exists |
| `attachment_scan_mode` | Virus scan config |
| `ai_enabled` | AI intake master toggle |
| `error_monitor_provider` | Error monitoring backend |
| `latest_migration` | Most recent applied migration name |
| `retention_candidates` | Count of expired deleted attachments |
| `degraded_components` | List of degraded subsystems |

## Metrics

**Admin only.** Requires `CookieJWTAuthentication` + `IsAdministrator`.

```http
GET /api/staff/operations/metrics/
```

**Purpose:** Aggregated operational metrics for monitoring dashboards.

**Response:**
```json
{
  "uptime_seconds": 3600,
  "users": {
    "total": 100,
    "patient": 60,
    "doctor": 30,
    "coordinator": 5,
    "administrator": 5
  },
  "consultations": {
    "submitted": 10,
    "accepted": 20,
    "cancelled": 5,
    "completed": 50
  },
  "attachments": {
    "by_status": {
      "not_required": 200,
      "pending": 0,
      "clean": 0,
      "quarantined": 0
    },
    "total_bytes": 10485760
  },
  "notifications_pending": 15,
  "retention_candidates": 3
}
```

**Errors:**
- Returns `503` with `{"error": "metrics_unavailable"}` if any query fails
