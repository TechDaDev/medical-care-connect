# Doctor Phase C acceptance

Acceptance evidence commands:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tests.test_doctor_phase_c tests.test_doctor_phase_b
python manage.py test tests.test_doctor_phase_c_postgres tests.test_doctor_phase_b_postgres
npm run lint
npm run typecheck
npm run test:run
npm run build
```

Coverage areas: assignment permissions, safe list/detail contracts, provenance, get-or-create idempotency, optimistic update, mass-assignment denial, validation, finalization immutability, patient projection, five outcome paths, transfer access, notifications, audits, query bounds, PostgreSQL races, localized navigation/list/editor, stale-input preservation, scoped caching, finalization dialog, print exclusions, and synthetic E2E flows.

Docker acceptance uses no-cache images `mcc-backend:doctor-phase-c` and `mcc-frontend:doctor-phase-c`. Test data must use `.test` users and synthetic narrative, then be removed with browser artifacts.
