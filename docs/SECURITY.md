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
