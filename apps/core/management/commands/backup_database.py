"""
Database backup command.

Usage:
  python manage.py backup_database              # dry-run
  python manage.py backup_database --execute     # real backup
  python manage.py backup_database --output-dir /path
  python manage.py backup_database --retain 14
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Backup PostgreSQL database using pg_dump."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", default=False,
                            help="Execute the backup (dry-run without this).")
        parser.add_argument("--output-dir", default="",
                            help="Override BACKUP_ROOT.")
        parser.add_argument("--retain", type=int, default=0,
                            help="Max backups to retain.")

    def handle(self, *args, **options):
        execute = options["execute"]
        output_dir = Path(options["output_dir"] or getattr(settings, "BACKUP_ROOT", ""))
        retain = options["retain"] or getattr(settings, "BACKUP_RETENTION_COUNT", 7)

        # Refuse SQLite
        db_engine = connection.vendor
        if db_engine != "postgresql":
            raise CommandError(f"Unsupported database engine: {db_engine}. Only PostgreSQL supported.")

        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)

        db_settings = settings.DATABASES["default"]
        db_name = db_settings["NAME"]
        db_user = db_settings["USER"]
        db_host = db_settings.get("HOST", "localhost")
        db_port = db_settings.get("PORT", "5432")
        db_pass = db_settings.get("PASSWORD", "")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"mcc_db_{timestamp}.dump"
        manifest_name = f"mcc_db_{timestamp}.manifest.json"
        backup_path = output_dir / filename
        manifest_path = output_dir / manifest_name

        self.stdout.write(f"Database: {db_name} on {db_host}:{db_port}")
        self.stdout.write(f"Output:   {backup_path}")
        self.stdout.write(f"Dry-run:  {'YES' if not execute else 'NO'}")

        if not execute:
            self.stdout.write(self.style.WARNING("Use --execute to create backup."))
            return

        # Verify pg_dump exists
        if not shutil.which("pg_dump"):
            raise CommandError("pg_dump not found. Install PostgreSQL client tools.")

        # Build pg_dump command — pass password via PGPASSWORD env
        env = os.environ.copy()
        if db_pass:
            env["PGPASSWORD"] = db_pass

        cmd = [
            "pg_dump",
            "--format=custom",
            "--compress=9",
            f"--file={backup_path}",
            f"--host={db_host}",
            f"--port={db_port}",
            f"--username={db_user}",
            db_name,
        ]

        self.stdout.write("Running pg_dump...")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            raise CommandError(f"pg_dump failed: {result.stderr.strip()}")
        if not backup_path.exists():
            raise CommandError("Backup file was not created.")

        # Checksum
        sha256 = hashlib.sha256()
        with open(backup_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        checksum = sha256.hexdigest()

        size_bytes = backup_path.stat().st_size

        # Manifest
        from django.db.migrations.recorder import MigrationRecorder
        migrations = list(
            MigrationRecorder.Migration.objects.order_by("-applied")
            .values_list("name", flat=True)[:5]
        )

        manifest = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "database_engine": db_engine,
            "application_version": getattr(settings, "APP_VERSION", "0.0.0"),
            "migrations": migrations,
            "backup_filename": filename,
            "size_bytes": size_bytes,
            "checksum_sha256": checksum,
            "environment": "production" if not settings.DEBUG else "development",
            "encrypted": False,
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Atomic rename for safety (already written directly, but keep for consistency)
        self.stdout.write(self.style.SUCCESS(f"Backup created: {backup_path} ({_fmt_size(size_bytes)})"))
        self.stdout.write(self.style.SUCCESS(f"Checksum (SHA-256): {checksum}"))
        self.stdout.write(self.style.SUCCESS(f"Manifest: {manifest_path}"))

        # Retention
        self._apply_retention(output_dir, retain, manifest_name)

    def _apply_retention(self, output_dir: Path, retain: int, current_manifest: str):
        """Remove older backups beyond retain count."""
        manifests = sorted(
            [p for p in output_dir.glob("*.manifest.json") if p.name != current_manifest],
            key=lambda p: p.stat().st_mtime,
        )
        to_remove = max(0, len(manifests) - (retain - 1)) if retain > 0 else 0
        for manifest_file in manifests[:to_remove]:
            dump_file = output_dir / manifest_file.name.replace(".manifest.json", ".dump")
            if dump_file.exists():
                dump_file.unlink()
                self.stdout.write(f"Removed old backup: {dump_file.name}")
            manifest_file.unlink()


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
