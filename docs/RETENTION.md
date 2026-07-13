# Attachment Retention & Purging

## Overview

Soft-deleted attachments (`ConsultationAttachment.deleted_at IS NOT NULL`) are
kept on disk for a configurable retention period. The
`purge_expired_attachments` management command permanently removes them.

## Command

```bash
# Dry-run (default) — shows what would be purged
python manage.py purge_expired_attachments

# Execute — actually deletes files and rows
python manage.py purge_expired_attachments --execute
```

## What It Does

1. Queries `ConsultationAttachment` where `deleted_at` is older than
   `ATTACHMENT_RETENTION_DAYS`.
2. For each match:
   - Deletes the underlying file from storage.
   - Hard-deletes the database row.
   - Records final audit event.
3. Processes in batches of `ATTACHMENT_PURGE_BATCH_SIZE` (default 500).

## Safety

- **Dry-run default** — `--execute` flag required for real deletion.
- **Batch processing** — limits transaction size.
- **Separate file deletion** — file removed before DB row to avoid orphaned
  rows pointing to missing files.
- **Audit trail** of purge run preserved.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ATTACHMENT_RETENTION_DAYS` | 90 | Days to keep deleted files |
| `ATTACHMENT_PURGE_BATCH_SIZE` | 500 | Rows per transaction |

## Scheduling

Recommended: run nightly via cron or Django-Q.

```cron
0 3 * * * /path/to/venv/bin/python /path/to/manage.py purge_expired_attachments --execute
```
