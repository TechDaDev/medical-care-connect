# Phase F E2E Testing

Local destructive acceptance permits only localhost, `127.0.0.1`, or hostnames explicitly listed in `E2E_APPROVED_HOSTS`. Backend fixture commands additionally require `DEBUG=true`, local database host, and local attachment storage.

## Setup

1. Start healthy PostgreSQL and apply migrations.
2. Copy frontend `.env.e2e.example` to `.env.e2e`.
3. Set `E2E_TEST_PASSWORD` locally. Never commit it.
4. From frontend repository run `npm run test:e2e`.

Playwright starts backend at `127.0.0.1:8000` and frontend preview at `127.0.0.1:4173`, waits for readiness, generates a unique run ID, seeds fixtures, runs desktop and mobile Chromium, and verifies cleanup.

Manual fixture commands:

```bash
E2E_TEST_PASSWORD='<local-only>' .venv/bin/python manage.py seed_e2e_data --run-id phase-f-local
.venv/bin/python manage.py cleanup_e2e_data --run-id phase-f-local
```

Fixtures include two administrators, coordinator, pending/approved/suspended doctors, patients, consultation states, privacy requests, audit event, specialty, clean/quarantined/rejected/retention attachments, message, and in-app notification. Every object carries run ID in a bounded synthetic field. Cleanup deletes only matching run artifacts and fails when any remain.

Failure artifacts live under ignored `test-results/`. Trace appears only on first retry; screenshots and video are failure-only.
