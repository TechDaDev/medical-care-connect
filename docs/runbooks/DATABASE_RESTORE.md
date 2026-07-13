# Runbook: Database Restore

## Symptoms

- Data loss (rows deleted, tables truncated)
- Data corruption (invalid values, constraint violations)
- Failed migration requiring rollback
- Accidental schema change

## Impact

- **Service down** during restore
- All writes rejected
- Read-only mode recommended during restore window

## Severity

- **Critical** — restore required for service recovery

## Actions

1. **Verify backup integrity:**
   ```bash
   python manage.py verify_backup --manifest /path/to/manifest.json
   ```

2. **Confirm environment:**
   ```bash
   python manage.py restore_backup --backup-manifest /path/to/manifest.json
   ```

3. **Identify the backup file:**
   ```bash
   ls -la $BACKUP_ROOT/mcc_db_*.dump
   ```

4. **Take app out of maintenance mode** (set `MAINTENANCE_MODE=true` env).

5. **Confirm target database name and host. Triple check.**

6. **Run pg_restore:**
   ```bash
   pg_restore --clean --if-exists \
     --dbname=postgresql://user:password@host:5432/dbname \
     /path/to/backup.dump
   ```

7. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

8. **Verify row counts:**
   ```bash
   python manage.py shell -c "
   from apps.accounts.models import User
   print(f'Users: {User.objects.count()}')
   "
   ```

9. **Restore attachment files** from attachment backup (see
   [ATTACHMENT_BACKUP.md](ATTACHMENT_BACKUP.md)).

10. **Run health and readiness checks:**
    ```bash
    curl http://localhost:8000/api/health/
    curl http://localhost:8000/api/readiness/
    ```

11. **Take app out of maintenance mode.**

## Validation

- Health endpoint returns `{"status": "healthy"}`
- Readiness returns `{"status": "ready"}`
- Row counts match pre-loss records
- Attachments downloadable

## Rollback

- Keep the corrupted state until restore is verified
- Do not delete the corrupted database until restored data is confirmed
- If restore fails, revert to previous backup image

## Privacy Precautions

- Never restore production data to non-production environments
- Never share backup files outside secure channels
- Backup files contain PII — treat as sensitive data
- Delete temporary restores after verification

## Related

- [DATABASE_BACKUP.md](DATABASE_BACKUP.md)
- [DISASTER_RECOVERY_TEST.md](../DISASTER_RECOVERY_TEST.md)
