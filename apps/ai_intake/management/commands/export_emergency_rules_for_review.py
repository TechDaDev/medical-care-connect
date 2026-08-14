from django.core.management.base import BaseCommand, CommandError

from apps.ai_intake.emergency_rules.review import export_review_csv


class Command(BaseCommand):
    help = "Export synthetic emergency-rule clinician review worksheet."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            count = export_review_csv(options["output"])
        except OSError as exc:
            raise CommandError("Could not write clinician review worksheet.") from exc
        self.stdout.write(f"Exported {count} unreviewed emergency rule rows.")
