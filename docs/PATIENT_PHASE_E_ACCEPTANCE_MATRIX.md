# Patient Phase E Acceptance Matrix

| Area | Backend | Frontend | Browser | Status |
|---|---|---|---|---|
| Dashboard | Phase A tests, 9 queries | dashboard unit suite | Phase A + axe | Accepted |
| Doctor discovery/create | Phase B tests, state checks | Phase B unit suite | Phase B + axe | Accepted |
| Consultation lifecycle | Phase C tests, Postgres race | Phase C unit suite | Phase C | Accepted |
| Profile/records | Phase D tests | Phase D unit suite | Phase D + axe | Accepted |
| Messages/notifications | Phase C/D tests | Phase C/D suites | Phase D + axe | Accepted |
| Export/deletion | privacy/Phase D tests | privacy suites | privacy + axe | Accepted |
| Permissions | object/role tests | route guards | permission suite | Accepted |
| CSRF/session | Phase 8A + Phase E tests | interceptor tests/build | storage test | Accepted |
| Accessibility | semantic contracts | lint/unit | axe + accesslint/manual | Accepted |
| Localization | safe locale contracts | EN/AR/CKB tests | RTL suites | Accepted |
| Performance | query ceilings | cache/build review | smoke | Accepted |
| Cleanup | seed/cleanup command | global hooks | aggregate zeros | Accepted |
| Dependencies | pip audit clean | React Router advisory reviewed | n/a | Accepted with tracked advisory |
| Containers | no-cache build + health/readiness | no-cache build + route/assets | local smoke | Accepted |
| Railway | health/readiness | public route | read-only production | Evidence required |

## Recorded Local Evidence

- Backend: 378 passed, 0 failed, 2 skipped on default SQLite; both retained
  skips passed separately against real PostgreSQL.
- Frontend unit: 144 passed, 0 failed, 0 skipped across 7 files.
- Playwright: 120 passed, 0 failed, 2 skipped across desktop and mobile.
- Retained Playwright skips are desktop exclusions for two mobile-only checks:
  Phase A mobile navigation/attention and Phase B mobile filter focus restore.
- Accessibility: Phase E axe checks passed on login and eight patient surfaces
  in desktop/mobile; accesslint reported zero login-page violations; manual
  390x844 landmark, heading, overflow, and keyboard checks passed.
- Dependencies: backend audit reported zero known vulnerabilities. Frontend
  production audit reports two high React Router RSC-mode advisories; current
  client-only SPA has no RSC/server-dom/source usage, and the suggested fix is a
  semver-major downgrade to 7.11.0. Advisory remains tracked, architecture not
  applicable.
- Containers: `mcc-backend:patient-phase-e` and
  `mcc-frontend:patient-phase-e` built without cache. Backend health/readiness
  and frontend root, patient fallback route, and static asset checks returned
  HTTP 200.

Railway row remains release-gated until pushed commits auto-deploy and read-only
production checks pass. No row may be marked accepted from intent alone.

Retained browser exclusions, if any, must name exact test, project, and reason.
Unsupported product architecture is documented, not silently simulated.
