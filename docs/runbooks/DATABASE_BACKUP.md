# Runbook: Database Backup

## Symptoms

- None (scheduled maintenance)
- Manual trigger for pre-deployment safety

## Impact

- None during normal operation
- Brief I/O on database during dump (negligible)

## Severity

- **Normal** — routine scheduled task

## Actions

1. Verify `BACKUP_ROOT` exists and writable:
   ```bash
   ls -la $BACKUP_ROOT
   ```

2. Run dry-run first:
   ```bash
   python manage.py backup_database
   ```

3. Execute backup:
   ```bash
   python manage.py backup_database --execute
   ```

4. Verify backup was created:
   ```bash
   ls -la $BACKUP_ROOT/mcc_db_*.dump
   ```

## Validation

```bash
python manage.py verify_backup
```

Expected: checksum OK, schema OK.

## Rollback

No rollback needed — backup is additive. Old backups are pruned by
retention policy. If a bad backup was created, delete it manually:

```bash
rm $BACKUP_ROOT/bad_backup.dump $BACKUP_ROOT/bad_backup.manifest.json
```

## Related

- [DATABASE_RESTORE.md](DATABASE_RESTORE.md)
- [BACKUP_AND_RESTORE.md](../BACKUP_AND_RESTORE.md)
