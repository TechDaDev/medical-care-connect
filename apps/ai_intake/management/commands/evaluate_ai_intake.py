import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ai_intake.evaluation import (
    EvaluationOptions,
    EvaluationSafetyError,
    load_dataset,
    run_evaluation,
)


class Command(BaseCommand):
    help = "Evaluate AI intake with synthetic data; mock provider is default."

    def add_arguments(self, parser):
        default_dataset = Path(__file__).resolve().parents[4] / "tests/fixtures/ai_intake_evaluation_cases.json"
        parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
        parser.add_argument("--dataset", default=str(default_dataset))
        parser.add_argument("--language", choices=["en", "ar", "ar-IQ", "ckb", "mixed"])
        parser.add_argument("--case-id")
        parser.add_argument("--max-cases", type=int, default=20)
        parser.add_argument("--output-json")
        parser.add_argument("--allow-live-provider", action="store_true")
        parser.add_argument("--allow-final-blinded", action="store_true")
        parser.add_argument("--patient-id")
        parser.add_argument("--consultation-id")
        parser.add_argument("--database-source", action="store_true")
        parser.add_argument("--fail-on-threshold", action="store_true")

    def handle(self, *args, **options):
        try:
            dataset = load_dataset(options["dataset"])
            report = run_evaluation(dataset, EvaluationOptions(
                provider=options["provider"],
                allow_live_provider=options["allow_live_provider"],
                language=options.get("language"),
                case_id=options.get("case_id"),
                max_cases=options["max_cases"],
                output_path=options.get("output_json"),
                patient_id=options.get("patient_id"),
                consultation_id=options.get("consultation_id"),
                database_source=options.get("database_source", False),
                allow_final_blinded=options.get("allow_final_blinded", False),
            ))
        except (EvaluationSafetyError, OSError, json.JSONDecodeError) as exc:
            raise CommandError(
                str(exc), returncode=getattr(exc, "exit_code", 4)
            ) from exc
        if options.get("output_json"):
            Path(options["output_json"]).write_text(
                json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
            )
        self.stdout.write(json.dumps({
            "run_id": report["run_id"], "provider": report["provider"],
            "case_count": report["case_count"], "metrics": report["metrics"],
        }, sort_keys=True))
        if report["provider"] == "deepseek" and report["metrics"]["cases_completed"] == 0:
            raise CommandError("Live provider unavailable for every case.", returncode=5)
        if options.get("fail_on_threshold") and not report["technical_acceptance_passed"]:
            raise CommandError("Evaluation completed below technical thresholds.", returncode=6)
