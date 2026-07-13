# Security

## Headers (production)

| Header | Value |
|--------|-------|
| Strict-Transport-Security | max-age=31536000; includeSubDomains; preload |
| X-Content-Type-Options | nosniff |
| X-Frame-Options | DENY |
| Referrer-Policy | same-origin |
| Cross-Origin-Opener-Policy | same-origin (via nginx) |

## Cookies (production)

- All auth cookies: `Secure`, `HttpOnly`, `SameSite=Lax`
- CSRF cookie: `Secure`, `SameSite=Lax` (not HttpOnly — JS reads it)

## JWT

- Access token: 5 min lifetime
- Refresh token: 24 h lifetime, blacklisted on logout
- Keys auto-generated via Django's `SECRET_KEY`
- No tokens in JSON response bodies (cookie-only)

## CSRF

- State-changing methods (POST/PUT/PATCH/DELETE) require `X-CSRFToken` header
- Token obtained via GET `/api/auth/csrf/`
- CSRF cookie: `mcc_csrftoken`

## CORS

- `CORS_ALLOW_CREDENTIALS=true` (required for cookies)
- Origins whitelist via `CORS_ALLOWED_ORIGINS`
- No wildcard in production

## Database

- PostgreSQL only in production (no SQLite fallback)
- Optional SSL via `DATABASE_SSL_REQUIRE`
- Connection pooling via `CONN_MAX_AGE` (default 0 in production)

## Production Checks

Run: `python manage.py check --deploy --settings=config.settings.production`

Requires:
- `SECRET_KEY` — must be set
- `ALLOWED_HOSTS` — no wildcard
- `POSTGRES_DB` — must be set (no SQLite)
- `CORS_ALLOWED_ORIGINS` — explicit
- `CSRF_TRUSTED_ORIGINS` — explicit

---

## Phase 8C: Observability Security

### Logging

- No request body, response body, cookies, auth headers, or JWT tokens are
  ever written to logs.
- No medical content, consultation descriptions, messages, notes, intake data,
  or attachment contents are logged.
- Remote IPs are one-way hashed with configurable salt (`LOG_IP_HASH_SALT`).
  Without salt, hashing is disabled.
- SafeLogger (`apps.core.logging.SafeLogger`) enforces field allowlisting.
  Any extra field whose key starts with `body`, `password`, `secret`, `token`,
  `cookie`, `auth`, `credential`, `medical`, `intake`, `message`, `note`, or
  `file_content` is silently dropped.

### Error Monitoring

- Default `DisabledErrorMonitor` does not send data to any external service.
- `SentryErrorMonitor` is reserved but not yet wired. When enabled, it **must**
  be configured to:
  - Strip request bodies
  - Strip cookies and auth headers
  - Strip PII via `before_send` callback
  - Never log credential data in context

### Backup Security

- Backup files contain PII and must be treated as sensitive data.
- Backup commands are **dry-run by default** — `--execute` required.
- `restore_backup` refuses to auto-restore to production.
- No encryption built-in yet (`BACKUP_REQUIRE_ENCRYPTION` defaults to `False`).
  Encrypted backups are reserved for future implementation.

### Privacy Export Limits

- Data exports include user profile, consultation metadata, and message
  history (as sender only).
- Medical records, doctor notes, and attachment file contents are excluded.
- Exports expire after `DATA_EXPORT_EXPIRY_DAYS` (default 7 days).
- Storage keys and checksums are never exposed via the privacy API.

### Anonymizer

- Current implementation is `PreviewOnlyAnonymizer` — preview reports what
  would be anonymized, deleted, or retained, but performs no destructive
  mutation.
- Medical records are always retained (legal compliance), reported as
  `blocked_by_retention`.
