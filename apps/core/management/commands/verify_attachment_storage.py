"""
Verify every active attachment's backing object exists and matches its recorded
SHA-256.  Optionally duplicate objects to a backup prefix.

Usage::

    python manage.py verify_attachment_storage
    python manage.py verify_attachment_storage --execute
    python manage.py verify_attachment_storage --execute --backup-missing
    python manage.py verify_attachment_storage --attachment-id <uuid>
"""

import hashlib
import io
import json
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.attachments.services.factory import get_storage_backend, clear_backend_cache


class Command(BaseCommand):
    help = "Verify attachment-object integrity and optionally back up to a secondary prefix."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", default=False)
        parser.add_argument("--backup-missing", action="store_true", default=False,
                            help="Copy missing objects to backup prefix.")
        parser.add_argument("--backup-all", action="store_true", default=False,
                            help="Copy all objects to backup prefix.")
        parser.add_argument("--attachment-id", default="",
                            help="Only verify a single attachment (UUID).")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--report-only", action="store_true", default=False)

    def handle(self, *args, **options):
        execute = options["execute"]
        backup_missing = options["backup_missing"]
        backup_all = options["backup_all"]
        single_id = options["attachment_id"]
        batch_size = options["batch_size"]
        report_only = options["report_only"]

        from apps.attachments.models import ConsultationAttachment

        queryset = ConsultationAttachment.objects.filter(
            is_deleted=False, status="AVAILABLE"
        ).exclude(storage_key="").exclude(storage_provider="").order_by("created_at")

        if single_id:
            queryset = queryset.filter(id=single_id)

        total = queryset.count()
        if total == 0:
            self.stdout.write("No active attachments to verify.")
            return

        self.stdout.write(f"Found {total} active attachment(s) to verify.")

        clear_backend_cache()
        backend = get_storage_backend()

        results = {
            "ok": 0,
            "missing": 0,
            "size_mismatch": 0,
            "checksum_mismatch": 0,
            "backed_up": 0,
            "errors": [],
        }

        for att in queryset.iterator(chunk_size=batch_size):
            status = self._verify_one(backend, att, results, execute)
            if status == "ok" and (backup_all or (backup_missing and status == "missing")):
                if execute and not report_only:
                    self._backup_one(backend, att, results)

        # Write manifest
        manifest = {
            "type": "attachment_verification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": getattr(settings, "ENVIRONMENT", ""),
            "total_checked": total,
            "results": {k: v for k, v in results.items() if k != "errors"},
            "errors": results["errors"][:50],
        }

        manifest_key = f"backups/manifests/attachment-verify-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        if execute:
            try:
                backend.save(io.BytesIO(json.dumps(manifest, indent=2).encode()), manifest_key)
                self.stdout.write(f"Manifest written to {manifest_key}")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Manifest upload failed: {exc}"))

        # Summary
        self.stdout.write("")
        self.stdout.write(f"OK:              {results['ok']}")
        self.stdout.write(f"Missing:         {results['missing']}")
        self.stdout.write(f"Size mismatch:   {results['size_mismatch']}")
        self.stdout.write(f"Checksum error:  {results['checksum_mismatch']}")
        self.stdout.write(f"Backed up:       {results['backed_up']}")
        if results["errors"]:
            self.stdout.write(self.style.WARNING(f"Errors: {len(results['errors'])}"))

        if results["missing"] or results["checksum_mismatch"]:
            raise CommandError(
                f"Integrity check FAILED: {results['missing']} missing, "
                f"{results['checksum_mismatch']} checksum errors."
            )

    def _verify_one(self, backend, att, results, execute):
        if not execute:
            return "ok"
        try:
            if not backend.exists(att.storage_key):
                results["missing"] += 1
                return "missing"

            if att.size_bytes:
                remote_size = backend.size(att.storage_key)
                if remote_size != att.size_bytes:
                    results["size_mismatch"] += 1
                    return "size_mismatch"

            if att.sha256:
                stream = backend.open(att.storage_key)
                h = hashlib.sha256()
                for chunk in iter(lambda: stream.read(65536), b""):
                    h.update(chunk)
                stream.close()
                if h.hexdigest() != att.sha256:
                    results["checksum_mismatch"] += 1
                    return "checksum_mismatch"

            results["ok"] += 1
            return "ok"
        except Exception as exc:
            results["errors"].append(f"{att.id}: {exc}")
            return "error"

    def _backup_one(self, backend, att, results):
        backup_key = f"backups/attachments/{att.id}.bin"
        try:
            data = backend.open(att.storage_key).read()
            backend.save(io.BytesIO(data), backup_key)
            results["backed_up"] += 1
        except Exception as exc:
            results["errors"].append(f"Backup failed {att.id}: {exc}")
