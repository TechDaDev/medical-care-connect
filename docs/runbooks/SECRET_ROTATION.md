# Runbook: Secret Rotation

## Symptoms

- Known or suspected key compromise
- Security audit finding
- Scheduled rotation requirement
- Developer with access leaves the team

## Impact

- **All existing sessions invalidated** when `SECRET_KEY` changes
- JWT tokens become invalid immediately
- Refresh tokens blacklisted
- DeepSeek API calls fail until new key is set
- All logged-in users must re-authenticate

## Severity

- **Critical** — requires communication to users about re-authentication

## Actions

### 1. Rotate Django SECRET_KEY

```bash
# Generate new key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Update environment variable and restart:

```bash
# Set new SECRET_KEY in Railway/env
# Restart backend
docker compose restart backend
```

**Impact:** All sessions invalidated. All users must log in again.

### 2. Rotate JWT Signing Key

The JWT signing key is derived from `SECRET_KEY`. Rotating `SECRET_KEY`
automatically rotates JWT signing.

No separate step needed.

### 3. Rotate DEEPSEEK_API_KEY

```bash
# Generate new key on DeepSeek dashboard
# Update DEEPSEEK_API_KEY in Railway/env
# No restart needed (read on next request)
```

**Impact:** In-flight AI intake sessions may fail. New sessions use new key.

### 4. Rotate LOG_IP_HASH_SALT

```bash
# Generate new random string
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Update `LOG_IP_HASH_SALT`. Old hashes in logs cannot be correlated.

### 5. Rotate Database Password

```bash
# Generate new password
python -c "import secrets; print(secrets.token_urlsafe(24))"

# Update PostgreSQL user password
docker compose exec db psql -U postgres -c \
  "ALTER USER mcc_user WITH PASSWORD 'new-password';"

# Update DATABASE_URL / POSTGRES_PASSWORD in environment
# Restart backend
docker compose restart backend
```

## Validation

- Login works with valid credentials
- JWT refresh works
- AI intake works (if enabled)
- Health/readiness pass
- Logs show no auth errors

## Communication

Notify users: "Scheduled maintenance complete. Please log in again."

## Related

- [COOKIE_AUTH_INCIDENT.md](COOKIE_AUTH_INCIDENT.md)
- [SERVICE_OUTAGE.md](SERVICE_OUTAGE.md)
