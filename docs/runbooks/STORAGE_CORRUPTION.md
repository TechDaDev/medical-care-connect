# Runbook: Storage Corruption

## Symptoms

- Attachment download returns 404 or 500
- Attachment download returns corrupted/empty file
- `verify_backup` reports checksum mismatch
- Users report "file unavailable" for previously working attachments

## Impact

- Patients/doctors cannot access shared files
- Medical evidence attachments unavailable
- May indicate underlying storage hardware issue

## Severity

- **High** — data loss potential if backups also affected

## Actions

### 1. Check storage backend

```bash
python manage.py shell -c "
from apps.attachments.services.factory import get_storage_backend
b = get_storage_backend()
print(type(b).__name__)
print('Root exists:', b._root.exists())
# Check for a specific attachment
from apps.attachments.models import ConsultationAttachment
att = ConsultationAttachment.objects.order_by('?').first()
if att:
    f = b.open(att.storage_key)
    print(f'File readable: {f is not None}')
    if f:
        data = f.read()
        print(f'Size: {len(data)} bytes')
        f.close()
"
```

### 2. Verify checksums from last backup

```bash
python manage.py verify_backup
```

### 3. Identify affected attachments

Check logs for attachment download errors:

```bash
docker compose logs backend | grep attachment
```

### 4. Restore from backup

If verified clean backup exists:

```bash
# Locate backup staging directory
ls -la $BACKUP_ROOT/attachments/

# Copy backup files back to storage root
# Manual: cp $BACKUP_ROOT/attachments/backup_20260115/*.bin <storage_root>/
```

### 5. Re-verify

```bash
python manage.py verify_backup
```

### 6. If backup also corrupted

- Check if storage hardware is failing (disk errors in system logs)
- Restore from the next oldest backup
- If no valid backup exists, data may be permanently lost

## Validation

- Specific affected files can be downloaded
- Checksum matches original
- No storage errors in logs

## Rollback

- Keep corrupted files until restore is confirmed
- Do not delete storage root until restore verified

## Related

- [ATTACHMENT_BACKUP.md](ATTACHMENT_BACKUP.md)
- [BACKUP_AND_RESTORE.md](../BACKUP_AND_RESTORE.md)
