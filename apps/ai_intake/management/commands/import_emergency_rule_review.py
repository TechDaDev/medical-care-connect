import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ai_intake.emergency_rules.registry import RULESET_VERSION
from apps.ai_intake.emergency_rules.review import ReviewValidationError, import_review_csv


class Command(BaseCommand):
    help = "Validate clinician dispositions without changing rule patterns or runtime status."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            records = import_review_csv(options["file"])
            counts = Counter(record["disposition"] for record in records)
            payload = {
                "ruleset_version": RULESET_VERSION,
                "rule_count": len(records),
                "reviewed_count": len(records) - counts["unreviewed"],
                "dispositions": dict(sorted(counts.items())),
                "records": records,
            }
            Path(options["output"]).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except (OSError, ReviewValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({
            "ruleset_version": RULESET_VERSION,
            "rule_count": len(records),
            "reviewed_count": payload["reviewed_count"],
        }, sort_keys=True))
