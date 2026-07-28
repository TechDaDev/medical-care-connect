from django.core.management.base import BaseCommand

from apps.core.e2e_data import cleanup


class Command(BaseCommand):
    help = "Remove one local patient acceptance fixture run and report aggregate counts."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True)

    def handle(self, *args, **options):
        counts = cleanup(options["run_id"])
        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic cleanup verified: "
                + ", ".join(f"{key}={value}" for key, value in counts.items())
            )
        )
