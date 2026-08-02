# Doctor privacy

Doctor endpoints:

- `GET /api/doctors/me/privacy/`
- `GET|POST /api/doctors/me/privacy/exports/`
- `GET /api/doctors/me/privacy/exports/:id/download/`
- `GET|POST /api/doctors/me/privacy/deletion/`
- `POST /api/doctors/me/privacy/deletion/:id/cancel/`

All objects scope to current doctor account. One active export and deletion request allowed. Downloads require owned, completed, unexpired export and return private/no-store ZIP without storage path or URL. Exports must not expose unrestricted patient medical data.

Deletion is administrator-controlled. Submission does not deactivate account or delete consultation, clinical, review, audit, or legally retained data. Pending requests alone may be cancelled. Audit excludes deletion reason.
