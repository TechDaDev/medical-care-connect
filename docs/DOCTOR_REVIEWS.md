# Doctor reviews

`GET /api/doctors/me/reviews/` returns owned reviews with one aggregate summary, pagination, response/rating/status/date filters, and stable ordering. Anonymous reviewer names are always null. Moderation reason, moderator identity, reports, and patient contact fields are excluded.

`POST|PATCH /api/doctors/me/reviews/:id/response/` requires approved doctor ownership and published review. One public response per review. Create/update require `client_request_id`; update additionally requires exact `expected_updated_at`. Database row locks, idempotency ledger, and conflict codes prevent duplicate or stale writes. Editing closes 72 hours after creation.

Response length: 10–2000 characters after normalization. Audit stores changed field names only. Patient notification contains generic text, never response body. Responses must not contain confidential patient information.
