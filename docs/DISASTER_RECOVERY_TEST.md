# Disaster Recovery Test Procedure

## Overview

Step-by-step DR test using a **temporary database** only. Never touches
production. Uses two separate temp databases to validate backup/restore.

## Prerequisites

- PostgreSQL client tools (`pg_dump`, `pg_restore`, `psql`)
- Write access to create databases on local PostgreSQL
- Backend virtual environment activated

## Step 1 — Create Temp Databases

```bash
# Create source temp DB
createdb -U mcc_user mcc_dr_source

# Create target temp DB (for restore target)
createdb -U mcc_user mcc_dr_target
```

Set environment to point at source DB:

```bash
export POSTGRES_DB=mcc_dr_source
```

## Step 2 — Seed Test Data

```bash
python manage.py migrate
python manage.py seed_data  # if available, or use test fixtures
```

Verify data exists:

```bash
python manage.py shell -c "
from apps.accounts.models import User
print(f'Users: {User.objects.count()}')
from apps.consultations.models import Consultation
print(f'Consultations: {Consultation.objects.count()}')
"
```

## Step 3 — Create Backup

```bash
python manage.py backup_database --execute --output-dir /tmp/dr_test
python manage.py backup_attachments --execute --output-dir /tmp/dr_test
```

## Step 4 — Verify Backup

```bash
python manage.py verify_backup --backup-dir /tmp/dr_test
```

Expected output: all checksums OK, no missing files.

## Step 5 — Restore to Separate Temp DB

**This step is intentionally not automated.** Run manually:

```bash
# Identify the backup file
ls -la /tmp/dr_test/mcc_db_*.dump

# Restore to target DB (not source!)
pg_restore --clean --if-exists \
  --dbname=postgresql://mcc_user:password@localhost:5432/mcc_dr_target \
  /tmp/dr_test/mcc_db_20260115_103000.dump
```

**WARNING:** Double-check the target database name. Never point at
`mcc_dr_source` or any production database.

## Step 6 — Verify Restored Data

```bash
# Set environment to target DB
export POSTGRES_DB=mcc_dr_target

python manage.py migrate  # Bring migrations to same state
python manage.py shell -c "
from apps.accounts.models import User
print(f'Restored users: {User.objects.count()}')
from apps.consultations.models import Consultation
print(f'Restored consultations: {Consultation.objects.count()}')
"
```

Compare counts against Step 2. They must match.

## Step 7 — Verify Attachments

If attachment backup was run:

```bash
python manage.py verify_backup --backup-dir /tmp/dr_test/attachments
```

## Step 8 — Destroy Temp Databases

```bash
dropdb -U mcc_user mcc_dr_source
dropdb -U mcc_user mcc_dr_target
rm -rf /tmp/dr_test
```

## Production Restore (for Real Incidents)

When restoring to production:

1. Take app out of maintenance mode
2. Verify backup manifest and environment match
3. Confirm the target database name is correct
4. Run: `pg_restore --clean --if-exists --dbname=<production_db> <backup.dump>`
5. Run: `python manage.py migrate`
6. Verify row counts match expected
7. Run: `python manage.py verify_backup --manifest <attachment_manifest>`
8. Run health and readiness checks
9. Restore attachment files from backup staging directory
10. Verify attachment checksums
11. Take app out of maintenance mode

## Never

- Run DR test against production
- Skip checksum verification
- Restore from untrusted backup files
- Share backup files outside secure channels
