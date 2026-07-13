# Backup & Restore

## Overview

Five management commands for PostgreSQL database and attachment file backup.

All commands are **dry-run by default** — add `--execute` to run.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ROOT` | `backups/` | Directory for backup files |
| `BACKUP_RETENTION_COUNT` | `7` | Number of backups to keep |

## Commands

### backup_database

Creates a compressed custom-format PostgreSQL dump (`pg_dump --format=custom
--compress=9`) with SHA-256 checksum and JSON manifest.

```bash
# Dry-run (shows what would happen)
python manage.py backup_database

# Execute backup
python manage.py backup_database --execute

# Override output directory
python manage.py backup_database --execute --output-dir /path/to/backups

# Override retention count
python manage.py backup_database --execute --retain 14
```

**Output files:**
- `mcc_db_YYYYMMDD_HHMMSS.dump` — compressed pg_dump
- `mcc_db_YYYYMMDD_HHMMSS.manifest.json` — metadata + checksum

**Prerequisites:**
- `pg_dump` must be installed (PostgreSQL client tools)
- Only PostgreSQL supported (refuses SQLite)
- Database password passed via `PGPASSWORD` env var

**Manifest format:**
```json
{
  "created_at": "2026-01-15T10:30:00.000Z",
  "database_engine": "postgresql",
  "application_version": "0.0.0",
  "migrations": ["001_initial", ...],
  "backup_filename": "mcc_db_20260115_103000.dump",
  "size_bytes": 1048576,
  "checksum_sha256": "abc123...",
  "environment": "development",
  "encrypted": false
}
```

### backup_attachments

Copies attachment files to a timestamped staging directory with integrity
verification.

```bash
# Dry-run
python manage.py backup_attachments

# Execute backup
python manage.py backup_attachments --execute

# Include soft-deleted attachments
python manage.py backup_attachments --execute --include-deleted

# Fail if any source file missing
python manage.py backup_attachments --execute --fail-on-missing
```

**Output:** Creates `{BACKUP_ROOT}/attachments/backup_YYYYMMDD_HHMMSS/`
directory containing:
- Individual `.bin` files named by attachment UUID
- `manifest.json` with per-file SHA-256, size, and status

The command:
1. Reads each attachment from current storage backend
2. Computes SHA-256 checksum
3. Compares against DB `sha256` field (warns on mismatch)
4. Copies to staging directory
5. Reports missing files

### verify_backup

Validates backup manifests and checksums without touching production data.

```bash
# Verify all manifests in BACKUP_ROOT
python manage.py verify_backup

# Verify a specific manifest
python manage.py verify_backup --manifest /path/to/manifest.json

# Scan a specific directory
python manage.py verify_backup --backup-dir /custom/path
```

**Verification checks:**
- Manifest JSON validity
- Required schema keys present
- Database dump SHA-256 matches manifest
- Attachment file checksums match manifest
- Object count consistency
- Version compatibility warning (backup vs current)

### restore_backup

**Verification only — does not auto-restore to production.**

```bash
# Verify manifest readiness
python manage.py restore_backup --backup-manifest /path/to/manifest.json

# Confirm environment match
python manage.py restore_backup --backup-manifest /path/to/manifest.json \
    --confirm-environment production
```

**Safety:**
- Refuses to execute automated restore to production
- Outputs the manual `pg_restore` command to run
- See `docs/DISASTER_RECOVERY_TEST.md` for restore procedure

### prune_backups

Removes old backups by count and/or age.

```bash
# Dry-run
python manage.py prune_backups

# Execute pruning
python manage.py prune_backups --execute

# Keep only 14 most recent
python manage.py prune_backups --execute --retain 14

# Remove backups older than 30 days
python manage.py prune_backups --execute --retain-days 30
```

**Safety:**
- Always keeps the latest valid backup
- Removes both `.dump` and `.manifest.json` together
- Dry-run by default

## Scheduling

Recommended cron schedule for production:

```cron
# Daily database backup at 2 AM
0 2 * * * cd /app && python manage.py backup_database --execute

# Weekly attachment backup at 3 AM Sunday
0 3 * * 0 cd /app && python manage.py backup_attachments --execute

# Daily prune at 4 AM
0 4 * * * cd /app && python manage.py prune_backups --execute
```
