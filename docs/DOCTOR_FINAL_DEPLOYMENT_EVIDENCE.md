# Doctor Final Deployment Evidence

## Policy

No manual Railway deploy is permitted for Phase E. Deployment observation is read-only. Production must correspond to pushed backend/frontend commit IDs before smoke evidence can close release.

## Evidence

- Railway project discovery: `MCC_Project` (`252bf51c-1705-4872-bd42-d771588ed799`).
- Railway service query: connector blocked by authorization; exact response was `Unauthorized. Please run railway login again.`
- Authorized GitHub deployment API fallback verified automatic Railway deployments.
- Local Docker backend image: `sha256:9690b519c155ba2cca8b527ac05a8815f3514439502cf636d7db8a021071488f`.
- Local Docker frontend image: `sha256:d81c3eef2b31eb91661a7fbc585eacb77559fc4e8bc9b5b3fa7e1691952a6596`.
- Local container smoke: both healthy; backend health/readiness 200; frontend root/intake/assets/API proxy 200; source map 404.
- Backend implementation commit `897c7115aea14a100d8177002c9455909a09bdde`: deployment `5711990812`; status record `16243896300`; `success` at 2026-08-02T07:59:41Z.
- Frontend commit `967b38137e10032a238a2d77393c2b39fe75e23e`: deployment `5711990808`; status record `16243898182`; `success` at 2026-08-02T07:59:49Z.
- Production backend `https://mccbackend-production.up.railway.app`: health 200, readiness 200, Doctor protected routes 401 for anonymous, JSON and security headers present.
- Production frontend route, asset, header, and source-map smoke: not run. Deployment payload exposes Railway project/environment only, repository contains no public hostname, and conservative service-derived candidates returned 404.

Automatic deployment gate: passed. Production smoke gate: `PARTIAL` because frontend runtime remains unverified.
