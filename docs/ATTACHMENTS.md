# Attachment System — Overview

## What It Does

Lets patients, doctors, and staff upload/download/delete files linked to a
consultation. Backend stores files outside static/media roots. Frontend lazy-
loads the attachment UI inside consultation detail pages.

## Key Concepts

- **ConsultationAttachment** — each file is one row (UUID PK, FK→Consultation).
- **Storage Backend** — provider-neutral ABC (`services/base.py`); current impl
  is `LocalProtectedStorageBackend` (`services/local.py`).
- **Scanned status** — every upload gets an initial scan status; scanning is
  currently disabled (all pass as `not_required`).
- **Soft delete** — `deleted_at` timestamp; admin can restore.
- **Audit trail** — every state change logged in `AttachmentAuditEvent`
  (immutable).

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST   | `/api/attachments/upload/` | Multipart upload |
| GET    | `/api/attachments/` | List attachments (filtered by consultation) |
| GET    | `/api/attachments/{id}/` | Detail (metadata only) |
| GET    | `/api/attachments/{id}/download/` | Stream file content |
| DELETE | `/api/attachments/{id}/` | Soft-delete |
| POST   | `/api/attachments/{id}/restore/` | Staff-only restore |

## Permission Model

- **Patient** — upload/download/delete own consultation attachments.
- **Doctor** — upload/download for assigned consultations; delete own uploads.
- **Staff** — full access (view all, delete any with reason).
- **Audit** — every delete/restore recorded with actor identity.

## Storage Settings

| Setting | Default | Notes |
|---------|---------|-------|
| `ATTACHMENT_LOCAL_ROOT` | `protected_attachments/` | Outside STATIC/MEDIA root |
| `ATTACHMENT_MAX_SIZE_MB` | 10 | Per-file limit |
| `ATTACHMENT_ALLOWED_EXTENSIONS` | pdf, jpg, jpeg, png | |
| `ATTACHMENT_SCAN_MODE` | `disabled` | Set to `clamav` for real scanning |
| `ATTACHMENT_RETENTION_DAYS` | 90 | Deleted files purged after this |
| `ATTACHMENT_PURGE_BATCH_SIZE` | 500 | Rows per purge cycle |

---

## Phase 8C: Backup & Storage Operations

### Backup Commands

| Command | Purpose |
|---------|---------|
| `backup_attachments` | Copies files to staging directory with checksums |
| `verify_backup` | Validates backup manifests and checksums |
| `restore_backup` | Verification only — does not auto-restore |

All commands are **dry-run by default** (`--execute` required).

See [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md) for full documentation.

### Storage Migration Skeleton

The storage backend uses a provider-neutral ABC (`services/base.py`) with
current implementation `LocalProtectedStorageBackend`. To migrate to a
different backend (e.g., S3, Railway Bucket):

1. Create new backend class inheriting from `StorageBackend`
2. Set `ATTACHMENT_STORAGE_BACKEND` to new backend name
3. Run `backup_attachments --execute` to snapshot current files
4. Run `verify_backup` to confirm integrity
5. Deploy new backend config
6. Restore files from backup to new backend
7. Verify checksums match

Backup commands work with any storage backend — they use the configured
backend via `get_storage_backend()`, not direct filesystem access.
