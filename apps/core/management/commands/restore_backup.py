"""
Restore backup skeleton — verifies but does not auto-restore.

Usage:
  python manage.py restore_backup \\
    --backup-manifest /path/to/manifest.json \\
    --confirm-environment production \\
    --execute

Current: verification only. Full restore requires documented manual procedure.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify and prepare for backup restoration. Not fully automated."

    def add_arguments(self, parser):
        parser.add_argument("--backup-manifest", required=True)
        parser.add_argument("--confirm-environment", default="")
        parser.add_argument("--execute", action="store_true", default=False)

    def handle(self, *args, **options):
        manifest_path = options["backup_manifest"]
        confirm_env = options["confirm_environment"]
        execute = options["execute"]

        import json
        from pathlib import Path

        mf = Path(manifest_path)
        if not mf.exists():
            raise CommandError(f"Manifest not found: {manifest_path}")

        data = json.loads(mf.read_text())
        env = data.get("environment", "unknown")
        current_env = "production" if not settings.DEBUG else "development"

        self.stdout.write(f"Backup environment: {env}")
        self.stdout.write(f"Current environment: {current_env}")

        if confirm_env and confirm_env != env:
            raise CommandError(f"Environment mismatch: backup={env}, confirm={confirm_env}")

        if execute and confirm_env == "production":
            self.stdout.write(self.style.ERROR(
                "Automated restore to production is intentionally blocked.\n"
                "See docs/DISASTER_RECOVERY_TEST.md for the safe restore procedure.\n"
                "Required manual steps:\n"
                "1. Take application out of maintenance mode\n"
                "2. Verify database name and host\n"
                "3. Run: pg_restore --clean --if-exists --dbname=<target> <backup.dump>\n"
                "4. Run: python manage.py migrate\n"
                "5. Verify record counts\n"
                "6. Run health/readiness checks\n"
                "7. Restore attachment files from attachment backup\n"
                "8. Verify attachment checksums\n"
                "9. Take application out of maintenance mode"
            ))
            return

        self.stdout.write(self.style.SUCCESS("Backup manifest verified. See docs/DISASTER_RECOVERY_TEST.md for restore procedure."))
