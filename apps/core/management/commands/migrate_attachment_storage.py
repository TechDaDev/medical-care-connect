"""
Storage migration command skeleton.

Usage:
  python manage.py migrate_attachment_storage \\
    --from-provider local \\
    --to-provider railway_bucket \\
    --dry-run

Current: validates arguments and checks provider availability only.
Future: will stream objects between providers.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


AVAILABLE_PROVIDERS = {"local"}


class Command(BaseCommand):
    help = "Migrate attachment storage between providers. Skeleton — no data copied yet."

    def add_arguments(self, parser):
        parser.add_argument("--from-provider", required=True)
        parser.add_argument("--to-provider", required=True)
        parser.add_argument("--dry-run", action="store_true", default=True)

    def handle(self, *args, **options):
        from_provider = options["from_provider"]
        to_provider = options["to_provider"]
        dry_run = options["dry_run"]

        if from_provider not in AVAILABLE_PROVIDERS:
            raise CommandError(f"Source provider '{from_provider}' not available. Available: {AVAILABLE_PROVIDERS}")

        if to_provider not in AVAILABLE_PROVIDERS:
            self.stdout.write(self.style.WARNING(
                f"Target provider '{to_provider}' is not yet available. "
                f"Available: {AVAILABLE_PROVIDERS}. "
                "No data will be copied until the adapter is implemented."
            ))
            return

        from apps.attachments.models import ConsultationAttachment
        total = ConsultationAttachment.objects.count()

        self.stdout.write(f"From:    {from_provider}")
        self.stdout.write(f"To:      {to_provider}")
        self.stdout.write(f"Objects: {total}")
        self.stdout.write(f"Dry-run: {'YES' if dry_run else 'NO'}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run complete. Use --no-dry-run when ready."))
            return

        self.stdout.write(self.style.SUCCESS(
            "Migration algorithm (future):\n"
            "1. Read source object\n"
            "2. Stream to target\n"
            "3. Verify size\n"
            "4. Verify SHA-256\n"
            "5. Update provider/key transactionally\n"
            "6. Add audit event\n"
            "7. Preserve source until verification\n"
            "8. Support resume checkpoint\n"
            "9. Support rollback\n"
            "10. Never expose credentials"
        ))
