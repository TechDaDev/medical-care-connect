"""Clean up Phase 11 E2E test data.

Usage:
    python manage.py cleanup_phase11_e2e --run-id <id> [--execute]
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.reviews.models import ConsultationReview, DoctorReviewResponse, ReviewReport


class Command(BaseCommand):
    help = "Clean Phase 11 E2E test data"

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True, help="Run identifier to clean")
        parser.add_argument("--execute", action="store_true", help="Actually delete records")

    def handle(self, *args, **options):
        run_id = options["run_id"]
        execute = options["execute"]

        if not run_id.isalnum() or len(run_id) > 32:
            raise CommandError("run-id must be alphanumeric, max 32 chars")

        suffix = f"-{run_id}@e2e.mcc.dev"
        qs = User.objects.filter(email__endswith=suffix)

        if not execute:
            self.stdout.write(self.style.WARNING("DRY RUN - add --execute to commit"))
            self.stdout.write(f"Users to delete: {qs.count()}")
            for u in qs:
                self.stdout.write(f"  {u.email} (role={u.role})")
            return

        with transaction.atomic():
            for u in qs:
                self.stdout.write(f"Deleting {u.email} (role={u.role})")
                u.delete()

            self.stdout.write(self.style.SUCCESS(f"Cleaned Phase 11 E2E data (run={run_id})"))
            self.stdout.write(f"  Users deleted: {qs.count()}")
