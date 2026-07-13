# Attachment Security

## Storage Isolation

- Files stored under `ATTACHMENT_LOCAL_ROOT` (default `protected_attachments/`).
- This directory is **outside** `STATIC_ROOT` and `MEDIA_ROOT`.
- Nginx/Django static file server does **not** serve this directory.
- **No public URL** — files accessible only through the authorized download
  endpoint.

## Download Authorization

The `download_attachment` view performs these checks:

1. **Authentication** — valid JWT required (via `JWTAuthentication`).
2. **Participation** — user must be a participant of the consultation
   (patient, assigned doctor, or staff).
3. **File status** — soft-deleted files return 404.
4. **Scan status** — quarantined/rejected files denied.
5. **Streaming response** — file content is streamed through Django;
   the backend never exposes the real filesystem path to the client.

## Upload Validation

- Extension whitelist (`ATTACHMENT_ALLOWED_EXTENSIONS`).
- MIME-type check against `libmagic` (python-magic).
- **Magic-byte signature** verification for PDF, JPEG, PNG.
- SHA-256 hash computed via streaming (safe for large files).
- Size limit enforced before any processing.

## Audit Trail

`AttachmentAuditEvent` records every state change:

| Actor | Action | Recorded |
|-------|--------|----------|
| User  | Upload | File hash, category, size |
| User  | Delete | Actor identity + timestamp |
| Staff | Restore | Actor identity + timestamp |
| System| Quarantine | Scan result |

Events are append-only (no update/delete).

## Future Railway Bucket

When switching to `RailwayBucketStorageBackend`:

- Signed URLs with short expiry.
- Server-side encryption at rest.
- Access logging via cloud provider.
- IAM roles instead of long-lived credentials.

## Soft Delete

- Deleted files remain on disk until the purge command runs.
- `restore_attachment` endpoint reverses soft-delete.
- Purge command requires `--execute` flag (dry-run by default).
- Retention period: `ATTACHMENT_RETENTION_DAYS` (default 90).
