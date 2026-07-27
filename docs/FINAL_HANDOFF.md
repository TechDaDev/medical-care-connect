# Phase F Handoff

## Architecture

Two repositories: Django/DRF backend and Vite/React frontend. GitHub `main` drives Railway automatic deployment. Administrative state is authoritative in backend services/models; frontend consumes available actions and redirects denied roles.

## Delivered hardening

- Required-dependency readiness semantics.
- Expanded administrator-safe Operations visibility.
- Deterministic local synthetic seed/cleanup with target guards.
- Local guarded Playwright topology, desktop/mobile Chromium, failure artifacts, and permission scenario.
- React Hook Form compiler warning fix.
- Frontend coverage scripts and measured baseline.
- Safe non-breaking dependency remediation.
- Administrative architecture, API, permission, E2E, Operations, security, and acceptance docs.

## Known limitations

- Notification model is in-app only.
- No persistent scanner-last-success record or real background-job model exists; API reports absence.
- React Router RSC advisory remains until compatible v8 migration/backport. Current SPA has no affected RSC execution path.
- Acceptance matrix records remaining browser mutation, focused accessibility, production, and deployment checks.
- Full WCAG certification is not claimed.

## Release procedure

Run all checks from each repository, remove artifacts, verify synthetic cleanup, inspect diffs/secrets, commit repositories separately, push GitHub only, wait for automatic Railway deployment, then perform read-only production smoke checks. Record exact counts, commits, deployment states, and unresolved matrix rows in release report.
