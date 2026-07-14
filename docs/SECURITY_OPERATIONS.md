# Security Operations

## Credential Rotation

See incident report for the 2026-07-14 credential-rotation event.

## Malware Scanning

### Architecture

```
Upload → quarantine (scan_pending) → ClamAV scan → clean → AVAILABLE
                                                → infected → QUARANTINED + deleted from storage
                                                → error → QUARANTINED (fail-closed)
```

### Scanner Abstraction

Two scanner implementations:

| Mode | Class | Behavior |
|------|-------|----------|
| `disabled` | `DisabledAttachmentScanner` | All files pass (dev/test) |
| `clamav` | `ClamavAttachmentScanner` | Scans via clamd INSTREAM over TCP |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ATTACHMENT_SCAN_MODE` | `disabled` | `disabled` or `clamav` |
| `CLAMAV_HOST` | — | Private Railway hostname |
| `CLAMAV_PORT` | `3310` | clamd TCP port |
| `CLAMAV_CONNECT_TIMEOUT` | `5` | Socket connection timeout (s) |
| `CLAMAV_READ_TIMEOUT` | `60` | Socket read timeout (s) |
| `CLAMAV_MAX_STREAM_BYTES` | `33554432` | Max bytes sent to clamd |

### Production Requirements

When `ATTACHMENT_SCAN_MODE=clamav`:
- `CLAMAV_HOST` and `CLAMAV_PORT` are required
- Backend will fail to start if ClamAV config is missing
- Readiness endpoint will report `scanner_available: false` if unreachable
- Uploads will be marked `QUARANTINED` on scanner failure (fail-closed)

### EICAR Verification

```bash
# From a Railway shell connected to ClamAV service:
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' | \
  clamdscan -
# Expected: "FOUND"
```

### Quarantine Policy

- Infected files: status=QUARANTINED, is_deleted=True, deleted from storage
- Scanner errors: status=QUARANTINED, scan_status=failed
- Manual review required for release

## Automated Backups

Two Railway Cron jobs execute scheduled backups:

### MCC_Database_Backup

- **Command**: `python manage.py run_scheduled_backup --execute`
- **Schedule**: Daily (UTC 01:00)
- **Output**: `backups/database/{run_id}.dump` in Storage_Bucket
- **Manifest**: `backups/manifests/{run_id}.manifest.json`
- **Verification**: SHA-256 checksum after upload
- **Retention**: 30 days (controlled by `BACKUP_DATABASE_RETENTION_DAYS`)

### MCC_Attachment_Verification

- **Command**: `python manage.py verify_attachment_storage --execute`
- **Schedule**: Daily (UTC 02:00)
- **Output**: Verification manifest in `backups/manifests/`
- **Failures**: Non-zero exit on missing/checksum mismatch

### Manual Backup

```bash
python manage.py run_scheduled_backup --execute
```

### Restore

See `docs/DISASTER_RECOVERY_TEST.md` for full restore procedure.

```bash
python manage.py verify_database_restore --backup-key backups/database/<run>.dump --execute
```

## Operations Status

Available at `GET /api/staff/operations/status/` (admin only):

| Field | Description |
|-------|-------------|
| `backup.storage_available` | Storage backend reachable |
| `backup.max_age_hours` | Backup freshness threshold |
| `scanner.mode` | `disabled` or `clamav` |
| `scanner.available` | Scanner service reachable |
| `degraded_components` | List of degraded systems |

## Deferred: Destructive Anonymization

Not implemented in this hardening phase.

**Prerequisites for future privacy phase:**
- Legal retention approval from compliance
- Backup-retention alignment (anonymize after retention period)
- Audit-log policy for anonymization events
- Attachment ownership policy (who can request anonymization)
- Dry-run mode required before any execution
- Approval workflow (two-person rule for destruction)
- Rollback: snapshots or backup-based recovery plan
