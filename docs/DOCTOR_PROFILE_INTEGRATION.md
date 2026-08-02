# Doctor profile integration

Existing `GET|PATCH /api/doctors/me/` remains authoritative. Read contract now includes `completeness`, `public_preview`, and doctor-relative availability/privacy links. Public preview uses existing public doctor serializer and is available only for approved active profile.

Update allowlist remains professional fields only. Approval state, license number/document, ownership, and audit fields cannot be mass-assigned. Personal account and professional profile saves remain separate so partial failure is visible. Frontend performs scoped cache updates for profile, current user, dashboard, and public directory.
