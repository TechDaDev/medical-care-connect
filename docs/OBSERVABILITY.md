# Observability

## Structured JSON Logging

All application logs emit as newline-delimited JSON. Configured via
`config/settings/base.py` using `apps.core.logging.JSONFormatter`.

### Logged Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 | UTC timestamp (`2026-01-15T10:30:00.000Z`) |
| `level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logger` | string | Logger name (`mcc`, `mcc.request`, `mcc.security`, `mcc.monitor`, `django`) |
| `event` | string | Short event name (e.g. `request.ok`, `security.auth.login.success`) |
| `environment` | string | `development`, `production` |
| `service` | string | Service name (default: `mcc-backend`) |
| `request_id` | string | Correlation UUID per request |
| `method` | string | HTTP method |
| `path_template` | string | URL path template (not parameterized) |
| `status_code` | int | HTTP response status |
| `duration_ms` | int | Request duration in milliseconds |
| `user_id` | string | Hashed user ID (empty for anonymous) |
| `role` | string | User role (`patient`, `doctor`, `coordinator`, `administrator`) |
| `remote_ip_hash` | string | First 16 chars of SHA-256 (salted) of remote IP |
| `user_agent_family` | string | First 80 chars of User-Agent |
| `error_code` | string | Error code for failures |
| `exception` | string | Exception repr (only when exc_info set) |

### Fields NEVER Logged

The following data is **never** written to logs:

- Request body / response body
- Passwords, credentials, secrets
- Cookie values (including session, CSRF)
- Authorization headers (`Authorization`)
- JWT tokens (access or refresh)
- CSRF token
- Attachment file contents
- Consultation descriptions or messages
- Medical records, intake data, or clinical notes
- Private doctor notes
- Original remote IP (only salted hash)
- DeepSeek API keys or prompts
- Any field whose key starts with: `body`, `request_body`, `response_body`,
  `password`, `secret`, `token`, `cookie`, `auth`, `credential`, `medical`,
  `intake`, `message`, `note`, `file_content`

### Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | `json` | `json` or `simple` (plain text) |
| `LOG_SERVICE_NAME` | `mcc-backend` | Value of `service` field |
| `LOG_INCLUDE_REQUESTS` | `true` | Enable per-request logging middleware |
| `LOG_SLOW_REQUEST_MS` | `1000` | Requests exceeding this (ms) log at WARNING |
| `LOG_IP_HASH_SALT` | `""` | Salt for IP hashing; **must** be set in production |

**IMPORTANT:** `LOG_IP_HASH_SALT` is a production security requirement.
Without a salt, IP hashes can be reversed via rainbow tables. Set to a
long random string.

## Request Correlation IDs

Every HTTP request receives a UUID correlation ID.

- If client sends `X-Request-ID` header with valid UUID v4, it is reused.
- Otherwise, a new UUID v4 is generated.
- ID is available as `request.request_id` in views/middleware.
- ID is returned in `X-Request-ID` response header.
- ID is included in every log line for that request.
- ID is included in error responses as `request_id` field.

Middleware: `apps.core.middleware.RequestIDMiddleware`

## Security Event Logging

Security events are logged via `apps.core.security_events` to the
`mcc.security` logger with event prefix `security.*`.

### Auth Events

| Event | Trigger | Extra Fields |
|-------|---------|--------------|
| `security.auth.login.success` | Successful login | `user_id`, `role`, `auth_method` |
| `security.auth.login.failed` | Failed login attempt | `reason` |
| `security.auth.logout` | User logout | `user_id` |
| `security.auth.refresh.failed` | Token refresh failure | `reason` |

### Request Security Events

| Event | Trigger | Extra Fields |
|-------|---------|--------------|
| `security.csrf.failed` | CSRF validation failed | `user_id`, `path` |
| `security.permission.denied` | Permission denied | `user_id`, `role`, `path`, `required_perm` |
| `security.throttle.exceeded` | Rate limit hit | `user_id`, `path`, `rate` |

### Attachment Events

| Event | Trigger | Extra Fields |
|-------|---------|--------------|
| `security.attachment.uploaded` | File uploaded | `attachment_id`, `consultation_id`, `user_id`, `category` |
| `security.attachment.downloaded` | File downloaded | `attachment_id`, `consultation_id`, `user_id` |
| `security.attachment.deleted` | File soft-deleted | `attachment_id`, `consultation_id`, `user_id` |
| `security.attachment.quarantined` | File quarantined | `attachment_id`, `reason` |

### Consultation Events

| Event | Trigger | Extra Fields |
|-------|---------|--------------|
| `security.consultation.transferred` | Doctor transfer | `consultation_id`, `from_doctor`, `to_doctor`, `by_user` |
| `security.consultation.priority_changed` | Priority change | `consultation_id`, `old_priority`, `new_priority`, `by_user` |

### Account Events

| Event | Trigger | Extra Fields |
|-------|---------|--------------|
| `security.account.deactivated` | Account deactivated | `user_id`, `by_user` |

### Data Events

| Event | Trigger | Extra Fields |
|-------|---------|--------------|
| `security.data.export.requested` | Export requested | `user_id` |
| `security.data.export.completed` | Export completed | `export_id` |

### Operations Events

| Event | Trigger | Extra Fields |
|-------|---------|--------------|
| `security.restore.executed` | Backup restore | `backup_type` |
| `security.backup.failed` | Backup failure | `backup_type`, `reason` |

## Error Monitoring

The `ErrorMonitor` interface (`apps.core.monitoring.base`) provides a
provider-neutral abstraction. Two implementations exist:

### DisabledErrorMonitor (Default)

No-op implementation that logs to `mcc.monitor` logger instead of sending
to an external service. Safe for all environments.

### SentryErrorMonitor (Reserved)

Sentry implementation is reserved but not yet wired. Configure via:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `ERROR_MONITOR_PROVIDER` | `disabled` | `disabled` or `sentry` |
| `ERROR_MONITOR_DSN` | `""` | Sentry DSN (required for `sentry`) |
| `ERROR_MONITOR_ENVIRONMENT` | `""` | Environment tag |
| `ERROR_MONITOR_RELEASE` | `""` | Release version tag |

### ErrorMonitor API

```python
from apps.core.monitoring.factory import get_error_monitor

monitor = get_error_monitor()
monitor.capture_exception(exception, context={})
monitor.capture_message("message", level="error", context={})
monitor.set_user(user_id="uuid", role="patient")
monitor.clear_user()
```

### Sanitization

When Sentry is enabled, the monitor must be configured to:
- Never send request bodies
- Never send cookies or auth headers
- Never send personal data (PII) in context
- Use `before_send` callback to strip sensitive fields
