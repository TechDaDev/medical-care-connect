"""Phase F v5 synthetic dataset and evaluator isolation checks."""

import hashlib
import importlib.util
from collections import Counter
from pathlib import Path

from django.test import SimpleTestCase

from apps.ai_intake.evaluation import (
    EvaluationOptions,
    _evaluation_messages,
    load_dataset,
    run_evaluation,
)

ROOT = Path(__file__).parent / "fixtures" / "ai_intake_eval_v5"
EXPECTED = {"en": 20, "ar": 20, "ar-IQ": 45, "ckb": 45, "mixed": 20}


def _builder():
    spec = importlib.util.spec_from_file_location("phase_f_dataset_builder", ROOT / "build_dataset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PhaseFDatasetTests(SimpleTestCase):
    def test_split_sizes_language_totals_and_independence(self):
        module = _builder()
        payloads = [module.build_split(split) for split in module.DISTRIBUTION]
        self.assertEqual([len(item["cases"]) for item in payloads], [70, 40, 40])
        totals = Counter(
            case["language"] for payload in payloads for case in payload["cases"]
        )
        self.assertEqual(totals, Counter(EXPECTED))
        contents = [
            case["turns"][0]["content"] for payload in payloads for case in payload["cases"]
        ]
        self.assertEqual(len(contents), len(set(contents)))
        hashes = [hashlib.sha256(text.encode()).hexdigest() for text in contents]
        self.assertEqual(len(hashes), len(set(hashes)))
        self.assertTrue(all(case["synthetic"] for payload in payloads for case in payload["cases"]))

    def test_materialized_splits_validate(self):
        self.assertEqual(len(load_dataset(ROOT / "development.json")["cases"]), 70)
        self.assertEqual(len(load_dataset(ROOT / "validation.json")["cases"]), 40)
        final = load_dataset(ROOT / "final_blinded.json")
        self.assertEqual(len(final["cases"]), 40)
        self.assertTrue(final["blinded"])
        self.assertFalse(final["tuning_allowed"])

    def test_expected_next_and_missing_labels_never_enter_provider_prompt(self):
        case = _builder().build_split("development")["cases"][0]
        case["expected"]["missing_blocking_fields"] = ["forbidden_fixture_marker"]
        case["expected"]["expected_next_fields"] = ["forbidden_fixture_marker"]
        prompt = str(_evaluation_messages(case))
        self.assertNotIn("forbidden_fixture_marker", prompt)

    def test_backend_target_metric_is_independent_of_provider_target(self):
        case = next(
            case for case in _builder().build_split("development")["cases"]
            if case["category"] == "question_selection"
        )
        case["mock_response"] = {
            "conversation_status": "needs_more_information",
            "patient_facing_message": "How severe is it?",
            "next_question": {"field": "onset", "text": "When did it begin?"},
            "extracted_updates": [],
            "uncertain_fields": [],
            "suggested_relevant_fields": [],
            "emergency_signal": {"detected": False, "level": "none", "reasons": []},
            "summary_for_review": None,
        }
        report = run_evaluation(
            {**_builder().build_split("development"), "cases": [case]},
            EvaluationOptions(max_cases=1),
        )
        result = report["results"][0]
        self.assertTrue(result["question_selection_correct"])
        self.assertTrue(result["question_target_fallback"])
        self.assertFalse(result["provider_target_correct"])
        self.assertNotEqual(result["backend_accepted_target"], "onset")
