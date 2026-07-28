# Patient E2E Testing

## Safety

Playwright accepts only `localhost`, `127.0.0.1`, or `::1` for frontend and API
targets. No allowlist override exists. Global setup seeds deterministic
synthetic fixtures; global teardown runs verified aggregate cleanup.

Required environment:

```bash
E2E_TEST_PASSWORD='<synthetic-only secret>' \
E2E_RUN_ID='phase-e-local' \
npx playwright test
```

Never print password. Never point suite at production.

## Fixture Coverage

Seed includes complete/incomplete/unrelated patients; approved/unavailable
doctors; active/inactive specialties; all 15 consultation statuses;
incomplete/confirmed/emergency intake; read/unread messages; pending/clean/
quarantined/rejected/retention attachments; finalized patient-safe record;
eligible completed consultation and review; notifications; pending/completed/
expired exports; pending/rejected deletion requests.

Every relational fixture is owned by synthetic users and carries run marker in
email, name, description, title, content, reason, slug, or storage key.

## Cleanup

```bash
.venv/bin/python manage.py cleanup_e2e_data --run-id phase-e-local
```

Command returns aggregate zero counts only. It covers users/profiles/doctors,
specialties, consultations, intake, messages/receipts, attachments/storage,
records/reviews, notifications, exports/archives, deletion requests, tokens,
sessions, audits, and request markers.

Browser suites cover Phases A–E and permission regressions. Phase E adds axe
WCAG A/AA automation and browser-storage token checks. Playwright artifacts are
temporary and must not be committed.
