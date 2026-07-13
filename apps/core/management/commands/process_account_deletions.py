"""
Process approved account deletion requests.

Usage:
  python manage.py process_account_deletions               # dry-run
  python manage.py process_account_deletions --execute      # process
  python manage.py process_account_deletions --batch-size 10
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.privacy.models import AccountDeletionRequest, DeletionStatus
from apps.core.anonymizer import PreviewOnlyAnonymizer


class Command(BaseCommand):
    help = "Process approved account deletion/anonymization requests."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", default=False)
        parser.add_argument("--batch-size", type=int, default=10)

    def handle(self, *args, **options):
        execute = options["execute"]
        batch_size = options["batch_size"]

        approved = AccountDeletionRequest.objects.filter(status=DeletionStatus.APPROVED)[:batch_size]
        total = approved.count()

        if total == 0:
            self.stdout.write("No approved deletion requests.")
            return

        self.stdout.write(f"Approved requests: {total}")
        self.stdout.write(f"Dry-run:           {'YES' if not execute else 'NO'}")

        anonymizer = PreviewOnlyAnonymizer()

        for req in approved:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(id=req.subject_user_id)
            except User.DoesNotExist:
                req.status = DeletionStatus.COMPLETED
                req.completed_at = timezone.now()
                req.save(update_fields=["status", "completed_at"])
                self.stdout.write(f"  {req.id}: user already deleted")
                continue

            preview = anonymizer.preview(user)

            self.stdout.write(f"\n  {req.id} — {user.email}")
            self.stdout.write(f"    Delete:   {', '.join(preview.to_delete) or 'none'}")
            self.stdout.write(f"    Anonymize: {', '.join(preview.to_anonymize) or 'none'}")
            self.stdout.write(f"    Retain:   {', '.join(preview.to_retain) or 'none'}")
            self.stdout.write(f"    Blocked:  {', '.join(preview.blocked_by_retention) or 'none'}")

            if not execute:
                continue

            # Preview mode only — no destructive execution
            req.status = DeletionStatus.SCHEDULED
            req.save(update_fields=["status"])

            self.stdout.write(self.style.WARNING(
                "  Scheduled (destructive execution not implemented — "
                "legal/medical retention rules required before automation)."
            ))

        if not execute:
            self.stdout.write(self.style.WARNING("Use --execute to schedule deletions."))
