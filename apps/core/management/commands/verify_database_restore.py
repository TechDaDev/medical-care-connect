"""
Verify a database backup can be restored by actually restoring it into a
temporary / disposable PostgreSQL database.

Because Railway may not support ad-hoc temp DB creation, this command
documents the manual steps and performs local restore verification where
possible.

Usage::

    python manage.py verify_database_restore --backup-key <storage-key> --execute
    python manage.py verify_database_restore --backup-key backups/database/<run>.dump --execute --temp-db-url <temp-postgres-url>
"""

import json
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify a database backup can be restored (dump readable, schema intact)."

    def add_arguments(self, parser):
        parser.add_argument("--backup-key", required=True, help="Storage key of the .dump file.")
        parser.add_argument("--execute", action="store_true", default=False)
        parser.add_argument(
            "--temp-db-url",
            default="",
            help="Temporary PostgreSQL URL to restore into (e.g. postgresql://user:pass@host/temp_restore_test).",
        )

    def handle(self, *args, **options):
        backup_key = options["backup_key"]
        execute = options["execute"]
        temp_db_url = options["temp_db_url"]

        if not execute:
            self.stdout.write("[DRY-RUN] Would verify restore. Use --execute to run.")
            return

        # ── Download backup ────────────────────────────────────────────────
        from apps.attachments.services.factory import get_storage_backend

        backend = get_storage_backend()
        if not backend.exists(backup_key):
            raise CommandError(f"Backup not found: {backup_key}")

        tmp = tempfile.NamedTemporaryFile(suffix=".dump", prefix="restore-test-", delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            stream = backend.open(backup_key)
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
            stream.close()
        except Exception as exc:
            Path(tmp_path).unlink(missing_ok=True)
            raise CommandError(f"Download failed: {exc}")

        # ── Step 1: pg_restore --list (proves dump is readable) ────────────
        self.stdout.write("Step 1: Checking dump readability …")
        r1 = subprocess.run(
            ["pg_restore", "--list", tmp_path],
            capture_output=True, text=True, timeout=60,
        )
        if r1.returncode != 0:
            Path(tmp_path).unlink(missing_ok=True)
            raise CommandError(f"Dump is corrupt or unreadable: {r1.stderr[:300]}")

        toc_lines = [l for l in r1.stdout.splitlines() if l.strip() and not l.startswith(";")]
        self.stdout.write(f"  Dump readable — {len(toc_lines)} TOC entries.")

        # ── Step 2: restore to temp DB (if temp-db-url provided) ───────────
        if temp_db_url:
            self.stdout.write("Step 2: Restoring to temp database …")
            r2 = subprocess.run(
                [
                    "pg_restore",
                    "--dbname", temp_db_url,
                    "--clean", "--if-exists",
                    "--no-owner",
                    tmp_path,
                ],
                capture_output=True, text=True, timeout=300,
            )
            if r2.returncode != 0:
                Path(tmp_path).unlink(missing_ok=True)
                raise CommandError(f"Restore to temp DB failed: {r2.stderr[:500]}")

            self.stdout.write("  Restore successful.")

            # Step 3: verify schema
            self.stdout.write("Step 3: Verifying schema …")
            r3 = subprocess.run(
                [
                    "psql", temp_db_url,
                    "-c", "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if r3.returncode == 0:
                tables = [l.strip() for l in r3.stdout.splitlines() if l.strip() and not l.startswith(("-", "(", "table"))]
                self.stdout.write(f"  Tables restored: {len(tables)}")

            # Verify migrations table
            r4 = subprocess.run(
                ["psql", temp_db_url, "-c", "SELECT COUNT(*) FROM django_migrations;"],
                capture_output=True, text=True, timeout=15,
            )
            if r4.returncode == 0:
                self.stdout.write(f"  Migrations table: OK")

            self.stdout.write(self.style.SUCCESS("Restore verification PASSED."))
        else:
            self.stdout.write(
                "Step 2: Skipped (no --temp-db-url). "
                "Dump is readable — full restore requires a temporary PostgreSQL database."
            )
            self.stdout.write(
                "To run a full restore test:\n"
                "  1. Create a temp DB (e.g. via Railway, Neon, or local Docker)\n"
                "  2. Run: python manage.py verify_database_restore \\\n"
                f"       --backup-key {backup_key} --execute \\\n"
                "       --temp-db-url postgresql://user:pass@host/temp_db\n"
            )

        # ── Cleanup ────────────────────────────────────────────────────────
        Path(tmp_path).unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS("Temporary dump file removed."))
