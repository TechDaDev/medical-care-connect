"""
Attachment backup command.

Usage:
  python manage.py backup_attachments               # dry-run
  python manage.py backup_attachments --execute      # real backup
  python manage.py backup_attachments --include-deleted
  python manage.py backup_attachments --fail-on-missing
"""

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.attachments.models import ConsultationAttachment
from apps.attachments.services.factory import get_storage_backend


class Command(BaseCommand):
    help = "Backup attachment files to staging directory."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", default=False)
        parser.add_argument("--output-dir", default="")
        parser.add_argument("--include-deleted", action="store_true", default=False)
        parser.add_argument("--fail-on-missing", action="store_true", default=False)

    def handle(self, *args, **options):
        execute = options["execute"]
        output_dir = Path(options["output-dir"] or (getattr(settings, "BACKUP_ROOT", "") + "/attachments"))
        include_deleted = options["include_deleted"]
        fail_on_missing = options["fail_on_missing"]

        output_dir.mkdir(parents=True, exist_ok=True)
        backend = get_storage_backend()

        qs = ConsultationAttachment.objects.all()
        if not include_deleted:
            qs = qs.filter(deleted_at__isnull=True)

        total = qs.count()
        self.stdout.write(f"Attachment objects to backup: {total}")
        self.stdout.write(f"Output dir: {output_dir}")
        self.stdout.write(f"Dry-run:    {'YES' if not execute else 'NO'}")

        if not execute:
            self.stdout.write(self.style.WARNING("Use --execute to copy files."))
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        staging = output_dir / f"backup_{timestamp}"
        staging.mkdir(parents=True, exist_ok=True)

        manifest_rows = []
        missing = 0
        copied = 0

        for att in qs.iterator():
            storage_key = att.storage_key
            if not storage_key:
                continue

            # Verify SHA-256
            try:
                f = backend.open(storage_key)
                if f is None:
                    raise FileNotFoundError
                content = f.read()
                f.close()
            except Exception:
                missing += 1
                if fail_on_missing:
                    raise CommandError(f"Missing object: {att.id}")
                self.stdout.write(self.style.WARNING(f"  MISSING {att.id}"))
                manifest_rows.append({
                    "id": str(att.id),
                    "storage_key": storage_key[-12:],
                    "size": 0,
                    "sha256": "",
                    "status": "missing",
                })
                continue

            sha256 = hashlib.sha256(content).hexdigest()

            # Verify against DB
            if att.sha256 and att.sha256 != sha256:
                self.stdout.write(self.style.WARNING(f"  SHA-256 mismatch: {att.id}"))

            # Copy to staging
            safe_name = f"{att.id}.bin"
            target = staging / safe_name
            with open(target, "wb") as out:
                out.write(content)

            copied += 1
            manifest_rows.append({
                "id": str(att.id),
                "storage_provider": getattr(settings, "ATTACHMENT_STORAGE_BACKEND", "local"),
                "opaque_key": storage_key[-12:],
                "size": len(content),
                "sha256": sha256,
                "status": att.status,
                "backup_file": safe_name,
            })

        # Write manifest
        manifest_data = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "total_objects": total,
            "copied": copied,
            "missing": missing,
            "include_deleted": include_deleted,
            "environment": "production" if not settings.DEBUG else "development",
            "attachments": manifest_rows,
        }
        manifest_path = staging / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)

        self.stdout.write(self.style.SUCCESS(f"Copied: {copied}, Missing: {missing}"))
        self.stdout.write(self.style.SUCCESS(f"Manifest: {manifest_path}"))
