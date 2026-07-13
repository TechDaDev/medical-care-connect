# Authentication

## HTTP-Only Cookie JWT (Primary)

Tokens stored in HTTP-only cookies — not accessible via JavaScript.

### Cookies

| Name | Purpose | HttpOnly | Secure | SameSite |
|------|---------|----------|--------|----------|
| `mcc_access` | Short-lived access token (5 min) | Yes | Prod only | Lax |
| `mcc_refresh` | Long-lived refresh token (24 h) | Yes | Prod only | Lax |
| `mcc_csrftoken` | CSRF token (state-changing requests) | No | Prod only | Lax |

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/login/` | Public | Login, sets cookies |
| POST | `/api/auth/register/patient/` | Public | Register, sets cookies |
| POST | `/api/auth/token/refresh/` | Cookie | Refresh access token |
| POST | `/api/auth/logout/` | Required | Clears cookies, blacklists refresh |
| GET | `/api/auth/csrf/` | Public | Sets CSRF cookie |
| GET/PATCH | `/api/accounts/me/` | Cookie/Bearer | Current user |

### CSRF Flow

1. Frontend GET `/api/auth/csrf/` → `mcc_csrftoken` cookie set
2. Frontend reads `mcc_csrftoken` from `document.cookie`
3. State-changing requests include `X-CSRFToken` header
4. Backend validates header matches cookie

### Bearer Compatibility

Legacy `Authorization: Bearer <token>` still supported for migration.

### Rate Limits

| Scope | Limit |
|-------|-------|
| Login | 10/min |
| Register | 5/hour |
| Token refresh | 30/min |
| AI intake | 30/hour |
| Default anon | 100/hour |
| Default user | 1000/hour |

Rates configurable via env vars (see `.env.example`).

---

## Phase 8C: Request ID in Error Responses

All API error responses now include a `request_id` field for correlation with
server-side logs.

**Example error response:**
```json
{
  "detail": "Authentication credentials were not provided.",
  "code": "not_authenticated",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

The `request_id` is:
- A UUID v4, generated per request
- Reused from `X-Request-ID` header if provided as valid UUID
- Returned in `X-Request-ID` response header
- Included in every structured log line for the request

This applies to all error codes: `validation_error`, `csrf_failed`,
`authentication_failed`, `not_authenticated`, `permission_denied`,
`not_found`, `method_not_allowed`, `throttled`, `conflict`, `api_error`,
`internal_error`.

The `request_id` is available in the frontend via the `X-Request-ID`
response header and inside error response JSON for debugging.
