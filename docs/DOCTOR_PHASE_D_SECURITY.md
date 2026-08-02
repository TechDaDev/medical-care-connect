# Doctor Phase D security review

Controls: approved-doctor permission, queryset ownership, recipient scoping, safe link allowlist, anonymous-name suppression, strict profile update serializer, row locks, idempotency keys, optimistic timestamps, protected export download, no-store headers, administrator-controlled deletion, bounded pagination, and content-free audits.

Reviewed attacks: cross-doctor message/review/export access; other-recipient notification updates; arbitrary redirects; anonymous identity leakage; approval/license mass assignment; stale/duplicate response writes; export storage disclosure; immediate destructive deletion; sensitive message/response/deletion content in audit.

No `csrf_exempt` added. Session CSRF behavior remains global. Synthetic-only browser mutation policy applies. No appointments, payments, prescriptions, insurance, external messaging, or video consultation added.
