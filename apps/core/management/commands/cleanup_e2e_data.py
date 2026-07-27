from django.core.management.base import BaseCommand

from apps.core.e2e_data import cleanup


class Command(BaseCommand):
    help = "Remove one local Phase F fixture run and verify zero artifacts remain."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True)

    def handle(self, *args, **options):
        cleanup(options["run_id"])
        self.stdout.write(self.style.SUCCESS("Synthetic cleanup verified: zero artifacts."))
