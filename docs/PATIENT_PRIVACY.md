# Patient Privacy

## Data Export

- List/create: `GET/POST /api/privacy/exports/`
- Detail: `GET /api/privacy/exports/:id/`
- Download: `GET /api/privacy/exports/:id/download/`

One active export per patient is enforced. Archives use private storage,
bounded lifetime, checksum, safe filename, `private, no-store`, and
`nosniff`. API never returns storage key or direct storage URL. Browser uses
blob download and revokes object URLs.

## Account State and Deletion

- Deactivate/reactivate account endpoints are explicit.
- Deletion request create/list/detail/cancel endpoints are ownership-scoped.
- Duplicate active deletion request is rejected.
- Request does not immediately erase account.
- Staff review workflow remains server-authoritative and audited.

## Acceptance Boundaries

Production smoke is read-only: no export creation, download, deactivation,
deletion, or cancellation. Synthetic local fixtures cover pending, completed,
expired export states and pending/rejected deletion states.

## Evidence

- Backend: `tests/test_patient_phase_d.py`, privacy and Phase 8 tests.
- Frontend: privacy unit suites.
- Browser: `e2e/privacy.spec.ts`, `e2e/patient-phase-d.spec.ts`.
- Export/deletion lookup ceiling: 4 queries.
