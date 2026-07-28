# Patient Final Handoff

## Delivered Scope

Patient Phases A–D form one SPA experience: dashboard, doctor discovery,
consultation creation/lifecycle/intake, messages, profile, medical records,
notifications, exports, deletion requests, localization, permissions, and
responsive navigation. Phase E adds closure hardening, race/security/
accessibility gates, deterministic fixtures, cleanup verification, and
canonical documentation.

## Operations

- Backend checks: Django check, migrations drift, SQLite suite, targeted real
  PostgreSQL concurrency suite, dependency audit.
- Frontend checks: clean install, lint, types, unit/coverage, production build,
  dependency audit, Playwright desktop/mobile, axe, accesslint.
- Containers: no-cache backend/frontend builds plus local health/readiness and
  frontend route smoke.
- Release: separate commits to each `main`; GitHub push triggers Railway.
  Railway verification is read-only. Never run manual deployment for Phase E.
- Final cleanup: run synthetic cleanup and retain aggregate-zero output only.

## Local Acceptance Snapshot

- Django: 378 passed, 0 failed, 2 skipped under SQLite. PostgreSQL concurrency
  and backup dry-run retained skips each passed against real PostgreSQL.
- Vitest: 144 passed, 0 failed, 0 skipped; coverage thresholds passed.
- Playwright: 120 passed, 0 failed, 2 skipped. Both skips are desktop
  exclusions for explicitly mobile-only interaction tests.
- Docker: `mcc-backend:patient-phase-e` and
  `mcc-frontend:patient-phase-e` no-cache builds passed; local HTTP smoke
  passed.
- Accessibility: axe desktop/mobile patient surface suite, accesslint login
  scan, and manual mobile landmark/overflow/keyboard review passed.

## Known Product Boundaries

In-app notifications only. No payments, prescriptions, appointments, video
consultations, external messaging, or production data mutation. Patient records
remain doctor-authored and patient-read-only. Accessibility checks are evidence,
not certification. React Router RSC advisory remains architecture-not-applicable
for current client-only SPA but stays dependency backlog.

Frontend image uses upstream nginx default root master process. Worker privilege
drop and read-only serving reduce exposure, but full non-root conversion is
broader infrastructure work; Phase E does not risk route/proxy destabilization.

## Rollback

Revert backend and frontend commits independently. Do not reset dirty worktrees.
Before rollback, inspect Railway deployment state and preserve audit evidence.
Schema rollback is unnecessary unless final migration check reports new
migrations; Phase E intends no schema changes.

## Completion Rule

Declare `COMPLETE` only when required local gates, cleanup, GitHub pushes,
Railway automatic deployments, health/readiness, and public read-only smoke all
pass. Otherwise declare `PARTIAL` and name failed evidence.
