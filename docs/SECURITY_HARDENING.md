# Phase F Security Hardening

## Controls

- Cookie JWT authentication plus centralized CSRF bootstrap/retry.
- Explicit backend role permissions and independent frontend route guards.
- Expected-state checks for concurrent administrative transitions.
- Self-lockout and final-active-administrator protection.
- Refresh-token revocation after role/status/session actions.
- Protected license/attachment downloads; no public storage locator.
- Audit metadata sanitization and formula-safe bounded CSV.
- Attachment release requires verified-clean scan state.
- Local E2E target, database, storage, and run-ID guards.
- Development seeding never prints login identifiers or shared passwords.

## Dependency status

Non-breaking lockfile updates remediate PostCSS path traversal and brace-expansion denial-of-service advisories.

Backend fixed-line updates: Django 5.1.15, Pillow 12.3.0, SimpleJWT 5.5.1, and PyJWT 2.13.0. `pip-audit -r requirements.txt` reports no known vulnerabilities after upgrade. Backend image builder upgrades pip to 26.1.2 before installing wheels. Pillow major-version compatibility is accepted only after full backend and image/attachment tests pass.

React Router advisory `GHSA-qwww-vcr4-c8h2` remains reported against v7.18.1. Fixed release is v8.3.0. This application uses browser SPA/Data Router APIs, no React Server Components, server actions, framework-mode request handler, or React Router server runtime; affected RSC action path is not present. Major v8 migration removes `react-router-dom` and requires planned compatibility work. Mitigation: keep Django CSRF enforcement authoritative, reject non-local E2E targets, avoid RSC adoption, monitor v7 backport, and test v8 migration separately.

Do not run `npm audit fix --force` without route/auth/redirect regression acceptance.

## Scanning

Run `npm audit --omit=dev`, `npm audit`, supported Python audit tooling, secret scanning, Django checks, frontend lint/type/build, full tests, and Docker builds. Never commit raw scan output containing sensitive values.
