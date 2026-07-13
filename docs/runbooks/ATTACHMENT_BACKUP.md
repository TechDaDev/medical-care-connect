# Runbook: Attachment Backup

## Symptoms

- None (scheduled maintenance)
- Pre-deployment precaution

## Impact

- None during normal operation
- CPU and I/O during backup proportional to file count

## Severity

- **Normal** — routine scheduled task

## Actions

1. Verify storage backend is configured:
   ```bash
   python manage.py shell -c "
   from apps.attachments.services.factory import get_storage_backend
   b = get_storage_backend()
   print(type(b).__name__)
   print(b._root.exists())
   "
   ```

2. Run dry-run:
   ```bash
   python manage.py backup_attachments
   ```

3. Execute backup (include deleted files if needed):
   ```bash
   python manage.py backup_attachments --execute
   ```

4. Or with fail-on-missing for critical backups:
   ```bash
   python manage.py backup_attachments --execute --fail-on-missing
   ```

## Validation

```bash
python manage.py verify_backup --backup-dir $BACKUP_ROOT
```

Expected: all file checksums OK, object count match.

## Rollback

No rollback needed — backup is additive. If a bad backup was created,
delete the staging directory:

```bash
rm -rf $BACKUP_ROOT/attachments/backup_*
```

## Related

- [STORAGE_CORRUPTION.md](STORAGE_CORRUPTION.md)
- [BACKUP_AND_RESTORE.md](../BACKUP_AND_RESTORE.md)
