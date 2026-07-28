import os

from django.core.management.base import BaseCommand, CommandError

from apps.core.e2e_data import seed


class Command(BaseCommand):
    help = "Create deterministic local-only patient acceptance fixtures."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True)

    def handle(self, *args, **options):
        password = os.environ.get("E2E_TEST_PASSWORD")
        if not password:
            raise CommandError("E2E_TEST_PASSWORD is required and is never printed.")
        counts = seed(options["run_id"], password)
        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic fixtures ready: "
                + ", ".join(f"{key}={value}" for key, value in counts.items())
            )
        )
