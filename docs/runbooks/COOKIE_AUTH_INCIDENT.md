# Runbook: Cookie/Auth Incident

## Symptoms

- Login returns success but subsequent requests fail
- CSRF errors in browser console
- "Authentication failed" errors in logs
- Frontend receives 403 on state-changing requests
- Users stuck in login loop

## Impact

- All users unable to authenticate
- No state-changing operations (create consultation, send messages, upload files)
- Read-only operations may still work (doctor directory, health check)

## Severity

- **Critical** — core auth flow broken

## Actions

### 1. Check cookie settings

Verify production settings are correct:

```python
SESSION_COOKIE_SECURE = True      # Must be True in production (HTTPS)
CSRF_COOKIE_SECURE = True          # Must be True in production (HTTPS)
SESSION_COOKIE_SAMESITE = "Lax"    # Must match frontend domain context
CSRF_COOKIE_SAMESITE = "Lax"       # Must match frontend domain context
SESSION_COOKIE_NAME = "mcc_access" # Must match frontend expectations
CSRF_COOKIE_NAME = "mcc_csrftoken" # Must match frontend expectations
```

### 2. Check CORS configuration

```bash
# On the backend container
python manage.py shell -c "
from django.conf import settings
print(f'CORS_ALLOWED_ORIGINS: {settings.CORS_ALLOWED_ORIGINS}')
print(f'CSRF_TRUSTED_ORIGINS: {settings.CSRF_TRUSTED_ORIGINS}')
print(f'CORS_ALLOW_CREDENTIALS: {settings.CORS_ALLOW_CREDENTIALS}')
"
```

- `CORS_ALLOWED_ORIGINS` must include frontend domain (no trailing slash)
- `CSRF_TRUSTED_ORIGINS` must include frontend domain (no trailing slash)
- `CORS_ALLOW_CREDENTIALS` must be `True`

### 3. Verify Secure flag in production

The `Secure` flag on cookies means the cookie is only sent over HTTPS.
If the frontend makes HTTP requests to an HTTPS backend (or vice versa),
the cookie won't be sent.

- Frontend must be served over HTTPS
- API requests must use HTTPS
- No mixed content

### 4. Check log for CSRF failures

```bash
docker compose logs backend | grep csrf.failed
```

### 5. Check log for auth failures

```bash
docker compose logs backend | grep auth.login.failed
```

### 6. Test auth flow manually

```bash
# Get CSRF token
curl -c /tmp/cookies.txt http://localhost:8000/api/auth/csrf/

# Login
curl -c /tmp/cookies.txt -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"..."}'

# Verify authenticated request
curl -b /tmp/cookies.txt http://localhost:8000/api/accounts/me/
```

## Evidence

Collect for debugging:
- Browser dev tools → Network tab → Request/Response headers
- Backend logs around the time of failure
- Browser console errors
- Steps to reproduce

## Related

- [SERVICE_OUTAGE.md](SERVICE_OUTAGE.md)
- [SECRET_ROTATION.md](SECRET_ROTATION.md)
