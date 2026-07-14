"""
Production scheduled database backup command.

Uploads a pg_dump to the configured storage backend under the
``backups/database/`` prefix.  Verifies the upload by SHA-256,
then removes the local temporary dump.

Usage::

    python manage.py run_scheduled_backup --execute
    python manage.py run_scheduled_backup --execute --run-id 20260715T010000Z
"""

import hashlib
import io
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Create a database dump and upload it to the configured storage backend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            default=False,
            help="Actually run the backup (dry-run without this flag).",
        )
        parser.add_argument(
            "--run-id",
            default="",
            help="Optional unique identifier for this backup run (default: auto timestamp).",
        )

    def _die(self, msg: str):
        raise CommandError(msg)

    def handle(self, *args, **options):
        execute = options["execute"]
        run_id = options["run_id"] or datetime.now(timezone.utc).strftime(
            "scheduled-%Y%m%dT%H%M%SZ"
        )

        # ── Safety: require --execute ─────────────────────────────────────
        if not execute:
            self.stdout.write("[DRY-RUN] Would create scheduled backup.  Use --execute to run.")
            return

        # ── Safety: refuse unsafe environments ────────────────────────────
        env = getattr(settings, "ENVIRONMENT", os.environ.get("RAILWAY_ENVIRONMENT_NAME", "development"))
        if env not in ("production",):
            self._die(f"Refusing to run scheduled backup in environment '{env}'.")

        # ── Safety: PostgreSQL only ───────────────────────────────────────
        db_vendor = connection.vendor
        if db_vendor != "postgresql":
            self._die(f"Refusing to run scheduled backup on {db_vendor}.")

        # ── Gather schema / migration state ───────────────────────────────
        from django.db.migrations.recorder import MigrationRecorder

        migration_count = MigrationRecorder(connection).applied_migrations().count()

        # ── Create temp dump ──────────────────────────────────────────────
        db_settings = settings.DATABASES["default"]
        db_name = db_settings["NAME"]
        db_user = db_settings.get("USER", "")
        db_host = db_settings.get("HOST", "")
        db_port = db_settings.get("PORT", "")
        db_password = db_settings.get("PASSWORD", "")

        tmp = tempfile.NamedTemporaryFile(
            suffix=".dump", prefix=f"backup_{run_id}_", delete=False
        )
        tmp_path = tmp.name
        tmp.close()

        env = os.environ.copy()
        if db_password:
            env["PGPASSWORD"] = db_password

        pg_args = [
            "pg_dump",
            f"--dbname=postgresql://{db_user}@{db_host}:{db_port}/{db_name}",
            "--format=custom",
            "--compress=9",
            "--no-owner",
            f"--file={tmp_path}",
        ]

        self.stdout.write(f"[BACKUP] Dumping database to temporary file …")
        start = time.time()

        try:
            result = subprocess.run(
                pg_args,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            self._cleanup(tmp_path)
            self._die("pg_dump timed out after 300 s.")
        except FileNotFoundError:
            self._cleanup(tmp_path)
            self._die("pg_dump not found on PATH.")

        if result.returncode != 0:
            stderr = (result.stderr or "")[:500]
            self._cleanup(tmp_path)
            self._die(f"pg_dump failed (exit {result.returncode}): {stderr}")

        elapsed = time.time() - start
        dump_size = Path(tmp_path).stat().st_size
        self.stdout.write(f"[BACKUP] Dump complete: {dump_size} bytes in {elapsed:.1f}s.")

        # ── SHA-256 ───────────────────────────────────────────────────────
        sha256_hash = hashlib.sha256()
        with open(tmp_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)
        checksum = sha256_hash.hexdigest()
        self.stdout.write(f"[BACKUP] SHA-256: {checksum[:16]}…{checksum[-16:]}.")

        # ── Build manifest ────────────────────────────────────────────────
        manifest = {
            "run_id": run_id,
            "type": "database",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "app_version": getattr(settings, "APP_VERSION", ""),
            "environment": env,
            "migration_count": migration_count,
            "dump_size_bytes": dump_size,
            "checksum_sha256": checksum,
            "storage_provider": "",
            "storage_key": "",
        }

        # ── Upload to storage backend ─────────────────────────────────────
        from apps.attachments.services.factory import get_storage_backend

        backend = get_storage_backend()
        storage_key = f"backups/database/{run_id}.dump"

        self.stdout.write(f"[BACKUP] Uploading to storage backend …")
        with open(tmp_path, "rb") as f:
            bio = io.BytesIO(f.read())

        try:
            stored = backend.save(bio, storage_key)
        except Exception as exc:
            self._cleanup(tmp_path)
            self._die(f"Upload failed: {exc}")

        manifest["storage_provider"] = stored.provider
        manifest["storage_key"] = stored.storage_key
        self.stdout.write(f"[BACKUP] Uploaded (provider={stored.provider}).")

        # ── Verify upload ─────────────────────────────────────────────────
        try:
            exists = backend.exists(stored.storage_key)
            if not exists:
                self._cleanup(tmp_path)
                self._die("Upload verification failed: object not found after upload.")

            stored_size = backend.size(stored.storage_key)
            if stored_size != dump_size:
                self._cleanup(tmp_path)
                self._die(
                    f"Upload verification failed: size mismatch "
                    f"(local={dump_size} remote={stored_size})."
                )

            # Stream verify SHA-256
            remote_stream = backend.open(stored.storage_key)
            verify_hash = hashlib.sha256()
            for chunk in iter(lambda: remote_stream.read(65536), b""):
                verify_hash.update(chunk)
            remote_stream.close()
            if verify_hash.hexdigest() != checksum:
                self._cleanup(tmp_path)
                self._die("Upload verification failed: SHA-256 mismatch.")
        except Exception as exc:
            self._cleanup(tmp_path)
            self._die(f"Upload verification error: {exc}")

        self.stdout.write(f"[BACKUP] Upload verified: size + SHA-256 match.")

        # ── Upload manifest ───────────────────────────────────────────────
        manifest_key = f"backups/manifests/{run_id}.manifest.json"
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        try:
            backend.save(io.BytesIO(manifest_bytes), manifest_key)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"[BACKUP] Manifest upload warning: {exc}"
            ))

        # ── Delete local temp ─────────────────────────────────────────────
        self._cleanup(tmp_path)
        self.stdout.write(self.style.SUCCESS(
            f"[BACKUP] Complete.  Key={stored.storage_key}"
        ))

    def _cleanup(self, path: str):
        try:
            os.unlink(path)
        except Exception:
            pass
