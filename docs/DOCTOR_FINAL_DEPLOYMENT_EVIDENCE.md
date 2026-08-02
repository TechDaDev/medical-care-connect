# Doctor Final Deployment Evidence

## Policy

No manual Railway deploy is permitted for Phase E. Deployment observation is read-only. Production must correspond to pushed backend/frontend commit IDs before smoke evidence can close release.

## Evidence

- Railway project discovery: `MCC_Project` (`252bf51c-1705-4872-bd42-d771588ed799`).
- Railway service query: blocked by connector authorization; exact response was `Unauthorized. Please run railway login again.`
- Local Docker backend image: `sha256:9690b519c155ba2cca8b527ac05a8815f3514439502cf636d7db8a021071488f`.
- Local Docker frontend image: `sha256:d81c3eef2b31eb91661a7fbc585eacb77559fc4e8bc9b5b3fa7e1691952a6596`.
- Local container smoke: both healthy; backend health/readiness 200; frontend root/intake/assets/API proxy 200; source map 404.
- Backend commit/deployment: commit handled by final Git evidence; Railway deployment ID/status/commit unavailable.
- Frontend commit/deployment: commit handled by final Git evidence; Railway deployment ID/status/commit unavailable.
- Production backend health and API smoke: not run because deployed commit identity could not be verified.
- Production frontend route, asset, header, and source-map smoke: not run because deployed commit identity could not be verified.

Current deployment gate: `PARTIAL`.
