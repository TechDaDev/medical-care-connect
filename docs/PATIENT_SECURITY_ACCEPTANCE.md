# Patient Security Acceptance

## Controls Reviewed

- Server-side role and object ownership on every patient resource.
- 404 anti-enumeration behavior for foreign objects.
- HttpOnly/Secure/SameSite cookie configuration and no token JSON/localStorage.
- CSRF on login, registration, refresh, and authenticated mutations.
- Refresh call primes CSRF and sends header.
- Throttles on authentication, privacy, intake, and sensitive writes.
- Stable safe error envelope; no secret, storage-key, prompt, or internal-note
  leakage.
- Private attachment/export delivery, `no-store`, `nosniff`, safe filenames,
  retention cleanup, and object URL revocation.
- Idempotency on consultation creation, message/intake answer, privacy request,
  and cancellation side effects.
- PostgreSQL row-lock race test for concurrent cancellation.
- E2E destructive target restricted to loopback.

## Attack Tree Summary

Primary patient threats: cross-account read/write, role-route bypass, CSRF,
token theft, identifier enumeration, duplicate mutation, unsafe upload/export,
private-field leakage, and production-targeted E2E cleanup. Controls above
block each path at server or safety boundary; browser guards remain secondary.

## Dependency Position

`uvx pip-audit -r requirements.txt` reports no known backend vulnerabilities.
`npm audit --omit=dev` reports two high findings through
`react-router-dom@7.18.1`: React Router RSC-mode CSRF action execution. Source
and dependency review found no React Server Components, server-dom packages, or
RSC action route. npm proposes downgrade to `7.11.0` and marks it semver-major;
Phase E does not take that destabilizing change. Advisory is reviewed,
architecture-not-applicable today, and tracked until safe upgrade path exists.

## Claim Boundary

Automated axe/accesslint and manual keyboard/responsive checks provide
acceptance evidence. They do not constitute legal, medical, security, or WCAG
certification. No production mutation is authorized by this document.
