# Doctor Phase D acceptance

Acceptance covers backend system/migration/full tests, PostgreSQL row-lock tests when configured, dependency audit, frontend lint/types/Vitest/coverage/build/audit, desktop/mobile Playwright with axe, backend/frontend Docker builds, graph re-index/trace, artifact review, separate commits, push to `main`, automatic Railway observation, and synthetic cleanup.

Required evidence: exact test counts, measured query counts, migration state, image IDs, commit hashes, deployment status if checked, and every skip/limitation. AccessLint requires reachable authenticated URL; axe is mandatory fallback but is not a WCAG certification.

Measured SQLite request-query bounds: messages 2, notifications 3, reviews 3, own profile 1, privacy overview 2, export history 2, deletion history 2. Page sizes are bounded at 50. These counts are asserted by acceptance tests.

Known product boundaries: notifications in-app only; deletion administrator-controlled; retained clinical/audit records may remain; exports exclude unrestricted patient records; no appointments, payments, prescriptions, insurance, external delivery, or video consultation. Doctor Phase E owns final cross-role release acceptance and unresolved production-only verification.
