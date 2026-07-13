"""
Backup verification command.

Usage:
  python manage.py verify_backup
  python manage.py verify_backup --manifest /path/to/manifest.json
"""

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify database and attachment backup manifests."

    def add_arguments(self, parser):
        parser.add_argument("--manifest", default="", help="Path to specific manifest.")
        parser.add_argument("--backup-dir", default="", help="Backup root directory.")

    def handle(self, *args, **options):
        backup_dir = Path(options["backup-dir"] or getattr(settings, "BACKUP_ROOT", ""))
        if not backup_dir.exists():
            raise CommandError(f"Backup directory not found: {backup_dir}")

        manifest_path = options["manifest"]
        if manifest_path:
            manifests = [Path(manifest_path)]
        else:
            manifests = sorted(backup_dir.glob("*.manifest.json"))
            # Also check attachment manifests
            att_dir = backup_dir / "attachments"
            if att_dir.exists():
                manifests.extend(sorted(att_dir.rglob("manifest.json")))

        if not manifests:
            self.stdout.write(self.style.WARNING("No manifests found."))
            return

        for mf in manifests:
            self.stdout.write(f"\nVerifying: {mf}")
            try:
                data = json.loads(mf.read_text())
            except (json.JSONDecodeError, IOError) as e:
                self.stdout.write(self.style.ERROR(f"  Invalid manifest: {e}"))
                continue

            # Schema validation
            required_keys = {"created_at"}
            if "checksum_sha256" in data:
                # DB backup manifest
                required_keys.update(["backup_filename", "database_engine"])
                dump_path = mf.parent / data.get("backup_filename", "")
                if dump_path.exists():
                    sha256 = hashlib.sha256()
                    with open(dump_path, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            sha256.update(chunk)
                    actual = sha256.hexdigest()
                    expected = data.get("checksum_sha256", "")
                    match = actual == expected
                    self.stdout.write(f"  Checksum: {'OK' if match else 'MISMATCH'}")
                    if not match:
                        self.stdout.write(self.style.WARNING(f"    Expected: {expected}"))
                        self.stdout.write(self.style.WARNING(f"    Actual:   {actual}"))
                else:
                    self.stdout.write(self.style.WARNING("  Dump file not found"))
            elif "attachments" in data:
                # Attachment backup manifest
                required_keys.update(["total_objects", "copied", "missing"])
                count_ok = data["total_objects"] == (data["copied"] + data["missing"])
                self.stdout.write(f"  Objects: {data['total_objects']}, Copied: {data['copied']}, Missing: {data['missing']}")
                self.stdout.write(f"  Count check: {'OK' if count_ok else 'MISMATCH'}")

                # Verify individual file checksums
                verified = 0
                failed = 0
                for att in data.get("attachments", []):
                    backup_file = att.get("backup_file", "")
                    if not backup_file:
                        continue
                    fp = mf.parent / backup_file
                    if fp.exists():
                        sha256 = hashlib.sha256(fp.read_bytes()).hexdigest()
                        if sha256 == att.get("sha256", ""):
                            verified += 1
                        else:
                            failed += 1
                    else:
                        failed += 1
                self.stdout.write(f"  File checksums: {verified} OK, {failed} FAILED")

            missing = required_keys - set(data.keys())
            if missing:
                self.stdout.write(self.style.WARNING(f"  Missing keys: {missing}"))
            else:
                self.stdout.write(f"  Schema: OK")

            # Version compatibility
            app_ver = data.get("application_version", "")
            current_ver = getattr(settings, "APP_VERSION", "0.0.0")
            if app_ver and app_ver != current_ver:
                self.stdout.write(self.style.WARNING(f"  Version mismatch: backup={app_ver}, current={current_ver}"))

        self.stdout.write(self.style.SUCCESS("\nVerification complete."))
