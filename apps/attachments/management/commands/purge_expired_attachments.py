"""Management command to purge expired soft-deleted attachments.

Usage:
    python manage.py purge_expired_attachments          # dry-run (default)
    python manage.py purge_expired_attachments --execute  # actually purge
    python manage.py purge_expired_attachments --batch-size 500
"""

from django.core.management.base import BaseCommand

from apps.attachments.services.retention import purge_expired


class Command(BaseCommand):
    help = "Purge soft-deleted attachments past their retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete. Without this flag, runs in dry-run mode.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of attachments to process per run (default: 100).",
        )

    def handle(self, *args, **options):
        dry_run = not options["execute"]
        batch_size = options["batch_size"]

        count = purge_expired(dry_run=dry_run, batch_size=batch_size)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY-RUN] {count} attachments eligible for purge. "
                    f"Use --execute to actually purge."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Purged {count} expired attachments."))
