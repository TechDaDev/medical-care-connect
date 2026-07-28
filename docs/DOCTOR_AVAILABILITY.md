# Doctor availability

Availability is recurring weekly availability, not calendar booking or
appointment scheduling. Model stores weekday string, local start/end time,
active flag, and timestamps. API reports configured Django timezone
(`Asia/Baghdad` in deployed configuration). No per-slot timezone or dated
occurrence exists, so API does not fabricate next available datetime.

Routes:

- `GET|POST /api/doctors/me/availability/`
- `PATCH|DELETE /api/doctors/me/availability/<slot-id>/`
- `PATCH /api/doctors/me/availability-status/`

Writes require approved active doctor ownership. Validation rejects unknown or
protected fields, equal ranges, cross-midnight ranges, exact duplicates, and
same-day overlaps. Transactions lock doctor profile row before conflict checks,
serializing concurrent writes on PostgreSQL. Updates and deletes support
`expected_updated_at`; stale writes return HTTP 409.

Accepting-status update locks doctor profile, supports `expected_updated_at`,
returns authoritative availability summary, and treats repeated value as
successful idempotent operation. Existing product semantics do not require an
active slot before enabling accepting status, so no new rule was invented.

Create/update/delete and changed accepting status emit privacy-safe database
audit events. Audit metadata contains identifiers, changed field names, and
accepting booleans only.
