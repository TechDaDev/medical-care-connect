# Doctor Final Security Review

## Boundaries

- Browser session uses secure cookie authentication; tokens must not enter local or session storage.
- Doctor approval and ownership checks execute on backend.
- Patient narrative, internal notes, storage locators, provider payloads, credentials, and raw audit context stay outside list projections.
- Download endpoints authorize ownership and safe attachment/export state before returning content.

## Attack tree

Goal: obtain or mutate clinical data without authorization.

- Bypass role or approval state
  - Direct deep-link request: backend approved-doctor permission returns 403.
  - Missing/suspended/rejected profile: access-state remains available; workspace remains denied.
- Cross tenant/object access
  - Guess consultation, record, message, review, export, deletion, or attachment ID: owned querysets conceal objects with 404.
  - Retain access after transfer: transaction changes owner; source loses access.
- Forge or replay write
  - Cross-site request: CSRF validation protects session writes.
  - Replay: client request IDs and action records make supported mutations idempotent.
  - Stale update: expected status/version/timestamp returns conflict.
- Exfiltrate through projection or link
  - Overshared list/detail: explicit serializers and Phase E recursive banned-field check.
  - Unsafe notification link: server derives links from allowlisted notification type and owned foreign keys.
  - Raw storage key: authenticated download endpoints mediate file access.
- Abuse synthetic fixtures
  - Non-local target or missing opt-in: seed, cleanup, and Playwright configuration refuse operation.

## Closure evidence

- Approved doctor succeeds; pending, rejected, suspended, missing-profile, patient, coordinator, and administrator principals receive 403; anonymous receives 401.
- Unrelated and transfer-source doctors receive ownership-concealing 404; transfer target succeeds.
- Recursive projection scan found no banned sensitive fields.
- Browser storage contained no bearer or refresh token; CSRF regression suite passed.
- Secret-pattern scan found no source match; image history contained no secret assignment pattern.
- Synthetic seed and cleanup require `E2E_LOCAL_ALLOWED=true` plus localhost safeguards.

Dependency state: Python runtime requirements have no reported advisory. Local Python tool environment reports six findings against `pip 24.0`. Frontend audit reports two high findings from one React Router advisory; no RSC, server action, or `react-server-dom-*` architecture exists, so vulnerable execution path is absent. Advisory remains visible and tracked.

Residual release risk: Railway deployment identity and production runtime remain unverified, not waived.
