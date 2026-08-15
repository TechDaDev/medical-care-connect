import ast
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.ai_intake.emergency_rules.registry import ALL_RULES, RULESET_VERSION
from apps.ai_intake.emergency_rules.review import (
    ReviewValidationError,
    export_review_csv,
    import_review_csv,
)
from apps.ai_intake.evaluation import (
    LEGACY_LIVE_DATASET_VERSION,
    EvaluationOptions,
    EvaluationSafetyError,
    load_dataset,
    run_evaluation,
)
from apps.ai_intake.services.deepseek import DeepSeekProvider
from apps.ai_intake.services.base import AIProviderUnavailable


FIXTURES = Path(__file__).parent / "fixtures"
LIVE_DATASET = FIXTURES / "ai_intake_live_eval_v2.json"


class PhaseCLiveEvaluationTests(SimpleTestCase):
    def setUp(self):
        self.dataset = load_dataset(LIVE_DATASET)

    def test_live_dataset_is_versioned_synthetic_and_bounded(self):
        self.assertEqual(self.dataset["version"], LEGACY_LIVE_DATASET_VERSION)
        self.assertEqual(len(self.dataset["cases"]), 20)
        self.assertTrue(all(case["synthetic"] is True for case in self.dataset["cases"]))
        self.assertEqual(
            {language: sum(case["language"] == language for case in self.dataset["cases"])
             for language in ("en", "ar", "ckb")},
            {"en": 11, "ar": 6, "ckb": 3},
        )

    def test_no_live_flag_is_refused_with_unsafe_exit_code(self):
        with self.assertRaises(EvaluationSafetyError) as caught:
            run_evaluation(self.dataset, EvaluationOptions(provider="deepseek"))
        self.assertEqual(caught.exception.exit_code, 3)

    @override_settings(AI_INTAKE_LIVE_EVAL_ENABLED=False)
    def test_disabled_environment_is_refused(self):
        with self.assertRaises(EvaluationSafetyError):
            run_evaluation(self.dataset, EvaluationOptions(
                provider="deepseek", allow_live_provider=True
            ))

    @override_settings(
        AI_INTAKE_LIVE_EVAL_ENABLED=True,
        DEEPSEEK_API_KEY="synthetic-key",
        DEEPSEEK_MODEL="deepseek-v4-flash",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
    )
    def test_production_and_identifiers_are_refused(self):
        base = dict(provider="deepseek", allow_live_provider=True, max_cases=1)
        for extra in (
            {"patient_id": "synthetic-id"},
            {"consultation_id": "synthetic-id"},
            {"database_source": True},
        ):
            with self.subTest(extra=extra), self.assertRaises(EvaluationSafetyError):
                run_evaluation(self.dataset, EvaluationOptions(**base, **extra))
        with patch.dict("os.environ", {"RAILWAY_ENVIRONMENT_ID": "production-marker"}):
            with self.assertRaises(EvaluationSafetyError):
                run_evaluation(self.dataset, EvaluationOptions(**base))

    @override_settings(
        AI_INTAKE_LIVE_EVAL_ENABLED=True,
        DEEPSEEK_API_KEY="synthetic-key",
        DEEPSEEK_MODEL="deepseek-v4-flash",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
    )
    def test_live_report_path_must_be_sanitized_tmp_json(self):
        with self.assertRaises(EvaluationSafetyError):
            run_evaluation(self.dataset, EvaluationOptions(
                provider="deepseek", allow_live_provider=True, max_cases=1,
                output_path=str(Path.cwd() / "unsafe-live-report.json"),
            ))

    @override_settings(
        AI_INTAKE_LIVE_EVAL_ENABLED=True,
        DEEPSEEK_API_KEY="synthetic-key",
        DEEPSEEK_MODEL="deepseek-v4-flash",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
        AI_INTAKE_EVAL_MAX_LIVE_CASES=2,
    )
    def test_excessive_live_case_count_is_refused(self):
        with self.assertRaises(EvaluationSafetyError):
            run_evaluation(self.dataset, EvaluationOptions(
                provider="deepseek", allow_live_provider=True, max_cases=3,
            ))

    @override_settings(AI_INTAKE_LIVE_EVAL_ENABLED=True)
    def test_invalid_live_provider_configuration_is_refused(self):
        variants = (
            {"DEEPSEEK_API_KEY": "", "DEEPSEEK_MODEL": "deepseek-v4-flash", "DEEPSEEK_BASE_URL": "https://api.deepseek.com"},
            {"DEEPSEEK_API_KEY": "synthetic-key", "DEEPSEEK_MODEL": "", "DEEPSEEK_BASE_URL": "https://api.deepseek.com"},
            {"DEEPSEEK_API_KEY": "synthetic-key", "DEEPSEEK_MODEL": "unknown-model", "DEEPSEEK_BASE_URL": "https://api.deepseek.com"},
            {"DEEPSEEK_API_KEY": "synthetic-key", "DEEPSEEK_MODEL": "deepseek-v4-flash", "DEEPSEEK_BASE_URL": "https://example.test"},
        )
        for settings_override in variants:
            with self.subTest(settings_override=settings_override), override_settings(**settings_override):
                with self.assertRaises(EvaluationSafetyError) as caught:
                    run_evaluation(self.dataset, EvaluationOptions(
                        provider="deepseek", allow_live_provider=True, max_cases=1,
                    ))
                self.assertEqual(caught.exception.exit_code, 2)

    @override_settings(
        AI_INTAKE_LIVE_EVAL_ENABLED=True,
        DEEPSEEK_API_KEY="synthetic-key",
        DEEPSEEK_MODEL="deepseek-v4-flash",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
    )
    def test_provider_failure_is_sanitized_per_case(self):
        provider = type("UnavailableProvider", (), {
            "max_tokens": 800,
            "retry_count": 2,
            "generate_structured_response": lambda self, messages: (_ for _ in ()).throw(
                AIProviderUnavailable("raw synthetic provider detail", safe_code="provider_timeout")
            ),
        })()
        with patch("apps.ai_intake.evaluation.DeepSeekProvider", return_value=provider):
            report = run_evaluation(self.dataset, EvaluationOptions(
                provider="deepseek", allow_live_provider=True, max_cases=1,
            ))
        body = json.dumps(report)
        self.assertEqual(report["metrics"]["provider_failures"], 1)
        self.assertIn("provider_timeout", body)
        self.assertNotIn("raw synthetic provider detail", body)
        self.assertNotIn("synthetic-key", body)

    def test_normal_mock_evaluation_never_constructs_live_provider(self):
        with patch("apps.ai_intake.evaluation.DeepSeekProvider") as provider:
            run_evaluation(self.dataset, EvaluationOptions(max_cases=1))
        provider.assert_not_called()

    def test_invalid_dataset_variants_are_refused(self):
        variants = [
            {"synthetic": False, "version": LEGACY_LIVE_DATASET_VERSION, "cases": []},
            {"synthetic": True, "version": LEGACY_LIVE_DATASET_VERSION, "cases": [{}]},
            {"synthetic": True, "version": LEGACY_LIVE_DATASET_VERSION, "cases": [
                {"case_id": "x", "dataset_version": LEGACY_LIVE_DATASET_VERSION,
                 "language": "en", "category": "x", "synthetic": False,
                 "turns": [], "expected": {}}
            ]},
        ]
        for payload in variants:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "dataset.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(payload=payload), self.assertRaises(EvaluationSafetyError):
                    load_dataset(path)

    def test_evaluator_has_no_patient_consultation_or_session_orm_import(self):
        source = Path("apps/ai_intake/evaluation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertFalse({"Patient", "Consultation", "AIIntakeSession"} & imports)
        self.assertNotIn(".objects", source)

    def test_mock_v2_report_has_phase_c_metrics_and_no_narratives(self):
        report = run_evaluation(self.dataset, EvaluationOptions(max_cases=20))
        self.assertEqual(report["case_count"], 20)
        self.assertIn("p50_latency_ms", report["metrics"])
        self.assertIn("total_tokens", report["metrics"])
        self.assertIn("thresholds", report)
        body = json.dumps(report)
        self.assertNotIn("Synthetic headache started", body)
        self.assertNotIn("system_policy", body)
        self.assertNotIn("base_url", body)

    @override_settings(
        DEEPSEEK_API_KEY="synthetic-key",
        DEEPSEEK_MODEL="deepseek-v4-flash",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
    )
    def test_structured_receptionist_call_disables_v4_thinking(self):
        provider = DeepSeekProvider()
        client = type("Client", (), {})()
        client.chat = type("Chat", (), {})()
        client.chat.completions = type("Completions", (), {})()
        with patch.object(client.chat.completions, "create", create=True) as create:
            provider._call_api(client, [{
                "role": "user", "content": "synthetic",
                "message_id": "00000000-0000-4000-8000-000000000001",
            }])
        self.assertEqual(
            create.call_args.kwargs["extra_body"],
            {"thinking": {"type": "disabled"}},
        )
        self.assertEqual(create.call_args.kwargs["messages"], [{
            "role": "user",
            "content": "[message_id: 00000000-0000-4000-8000-000000000001]\nsynthetic",
        }])

    @override_settings(
        AI_INTAKE_LIVE_EVAL_ENABLED=True,
        DEEPSEEK_API_KEY="",
        DEEPSEEK_MODEL="",
    )
    def test_management_command_uses_stable_error_code(self):
        with self.assertRaises(CommandError) as caught:
            call_command(
                "evaluate_ai_intake", provider="deepseek", allow_live_provider=True,
                dataset=str(LIVE_DATASET), max_cases=1,
            )
        self.assertEqual(caught.exception.returncode, 2)


class EmergencyClinicianReviewWorkflowTests(SimpleTestCase):
    def test_export_contains_every_rule_and_required_fields(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "review.csv"
            count = export_review_csv(path)
            rows = list(csv.DictReader(path.open(encoding="utf-8")))
        self.assertEqual(count, len(ALL_RULES))
        self.assertEqual(len(rows), len(ALL_RULES))
        required = {
            "rule_id", "rule_code", "ruleset_version", "language", "severity",
            "pattern", "pattern_type", "positive_examples", "negative_examples",
            "negation_examples", "historical_examples", "family_context_examples",
            "enabled", "clinician_review_status", "reviewer", "reviewer_role",
            "review_date", "disposition", "review_notes",
        }
        self.assertTrue(required <= set(rows[0]))
        self.assertTrue(all(row["positive_examples"] for row in rows))
        self.assertTrue(all(row["negative_examples"] for row in rows))

    def _export(self, directory):
        path = Path(directory) / "review.csv"
        export_review_csv(path)
        return path

    def _rewrite_first(self, path, **changes):
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        rows[0].update(changes)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_valid_unreviewed_import_preserves_patterns_and_enabled_state(self):
        with TemporaryDirectory() as directory:
            path = self._export(directory)
            records = import_review_csv(path)
        self.assertEqual(len(records), len(ALL_RULES))
        by_id = {rule.rule_id: rule for rule in ALL_RULES}
        self.assertTrue(all(record["pattern"] == by_id[record["rule_id"]].pattern for record in records))
        self.assertTrue(all(record["enabled"] == by_id[record["rule_id"]].enabled for record in records))

    def test_invalid_disposition_unknown_rule_and_version_mismatch_are_rejected(self):
        changes = (
            {"disposition": "clinically_validated"},
            {"rule_id": "unknown-rule"},
            {"ruleset_version": "mcc-emergency-rules-v999"},
            {"pattern": "silently changed"},
            {"enabled": "false"},
        )
        for change in changes:
            with TemporaryDirectory() as directory:
                path = self._export(directory)
                self._rewrite_first(path, **change)
                with self.subTest(change=change), self.assertRaises(ReviewValidationError):
                    import_review_csv(path)

    def test_approved_or_rejected_requires_reviewer_and_date(self):
        for disposition in ("approved", "approved_with_changes", "rejected"):
            with TemporaryDirectory() as directory:
                path = self._export(directory)
                self._rewrite_first(path, disposition=disposition, reviewer="", review_date="")
                with self.subTest(disposition=disposition), self.assertRaises(ReviewValidationError):
                    import_review_csv(path)

    def test_management_commands_export_and_validate_without_runtime_mutation(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "review.csv"
            output = Path(directory) / "validated.json"
            before = [(rule.rule_id, rule.pattern, rule.enabled) for rule in ALL_RULES]
            call_command("export_emergency_rules_for_review", output=str(source))
            call_command("import_emergency_rule_review", file=str(source), output=str(output))
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["ruleset_version"], RULESET_VERSION)
        self.assertEqual(payload["reviewed_count"], 0)
        self.assertEqual(before, [(rule.rule_id, rule.pattern, rule.enabled) for rule in ALL_RULES])
