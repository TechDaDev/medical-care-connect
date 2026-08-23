import csv
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.ai_intake.emergency_rules.review import (
    ReviewValidationError,
    export_review_csv,
    import_review_csv,
)
from apps.ai_intake.evaluation import (
    EvaluationOptions,
    EvaluationSafetyError,
    _evaluate_case,
    load_dataset,
    run_evaluation,
)
from apps.ai_intake.services.semantic_validation import (
    grounding_classification,
    grounding_evidence,
    normalize_grounding_text,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ai_intake_eval_v4"
SPLIT_FILES = {
    "development": FIXTURE_ROOT / "development.json",
    "validation": FIXTURE_ROOT / "validation.json",
    "final": FIXTURE_ROOT / "final_blinded.json",
}


class PhaseEDatasetTests(SimpleTestCase):
    def test_v4_distribution_and_blinding(self):
        datasets = {name: load_dataset(path) for name, path in SPLIT_FILES.items()}
        self.assertEqual(
            {name: len(dataset["cases"]) for name, dataset in datasets.items()},
            {"development": 60, "validation": 30, "final": 30},
        )
        cases = [case for dataset in datasets.values() for case in dataset["cases"]]
        self.assertEqual(Counter(case["language"] for case in cases), {
            "en": 20, "ar": 20, "ar-IQ": 35, "ckb": 35, "mixed": 10,
        })
        self.assertTrue(all(case["dataset_version"] == "mcc-ai-intake-eval-v4" for case in cases))
        self.assertTrue(all(case["synthetic"] is True for case in cases))
        self.assertTrue(datasets["final"]["blinded"])
        self.assertFalse(datasets["final"]["tuning_allowed"])
        with self.assertRaises(EvaluationSafetyError):
            run_evaluation(datasets["final"], EvaluationOptions(max_cases=30))

    def test_v4_has_required_language_hardening_categories(self):
        cases = [
            case
            for path in SPLIT_FILES.values()
            for case in load_dataset(path)["cases"]
        ]
        required = {
            "extraction", "duration", "onset", "severity", "location",
            "medication", "allergy", "negation", "uncertainty", "correction",
            "spelling", "fragmented", "long_answer", "prompt_injection",
            "hallucination", "emergency_override",
        }
        for language in ("ar-IQ", "ckb"):
            self.assertTrue(required <= {
                case["category"] for case in cases if case["language"] == language
            })

    def test_v4_rejects_final_dataset_metadata_tampering(self):
        payload = json.loads(SPLIT_FILES["final"].read_text(encoding="utf-8"))
        payload["tuning_allowed"] = True
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(EvaluationSafetyError):
                load_dataset(path)

    def test_evaluator_reports_spans_language_safety_and_review_status(self):
        report = run_evaluation(
            load_dataset(SPLIT_FILES["development"]),
            EvaluationOptions(max_cases=60),
        )
        self.assertEqual(report["clinical_review"]["rule_count"], 56)
        self.assertEqual(report["clinical_review"]["status"], "unreviewed")
        for summary in report["metrics"]["per_language"].values():
            self.assertIn("unsupported_field_acceptances", summary)
            self.assertIn("hallucination_acceptances", summary)
            self.assertIn("emergency_bypasses", summary)

    def test_evaluator_records_sanitized_grounding_span(self):
        message_id = "00000000-0000-4000-8000-000000009200"
        case = {
            "case_id": "unit-phase-e-span",
            "dataset_version": "mcc-ai-intake-eval-v4",
            "split": "development",
            "language": "ar-IQ",
            "category": "duration",
            "synthetic": True,
            "turns": [{"role": "user", "content": "صارلي يومين", "message_id": message_id}],
            "expected": {"supported_fields": ["duration"], "expected_language": "ar"},
            "mock_response": {
                "conversation_status": "needs_more_information",
                "patient_facing_message": "شكد شدة الأعراض؟",
                "next_question": {"field": "severity", "text": "شكد شدة الأعراض؟"},
                "extracted_updates": [{
                    "field": "duration", "value": "2 days",
                    "source_message_ids": [message_id], "certainty": "explicit",
                }],
                "uncertain_fields": [], "suggested_relevant_fields": [],
                "emergency_signal": {"detected": False, "level": "none", "reasons": []},
                "summary_for_review": None,
            },
        }
        result = _evaluate_case(case, None)
        self.assertEqual(
            result["grounding_assessments"][0]["classification"],
            "structured_numeric",
        )
        self.assertEqual(result["grounding_assessments"][0]["evidence_span"], {"start": 0, "end": 11})


class PhaseEGroundingTests(SimpleTestCase):
    @staticmethod
    def update(field, value):
        return SimpleNamespace(field=field, value=value)

    def test_iraqi_field_scoped_canonicalization(self):
        cases = (
            ("duration", "2 days", "صارلي يومين"),
            ("onset", "yesterday", "من البارحة بلش"),
            ("severity", "severe", "الوجع كلش قوي"),
            ("severity", "mild", "الوجع مو قوي"),
            ("location", "back", "الوجع بظهري"),
            ("current_medications", ["paracetamol"], "اخذ بانادول"),
            ("allergies", ["penicillin"], "عندي حساسية من البنسلين"),
            ("chief_complaint", "صداع", "راسي يوجعني"),
            ("severity", "شديد جداً", "الوجع كلش قوي"),
            ("duration", "5 أيام", "صارلي خمس أيام"),
            ("allergies", ["لا يوجد"], "ما عندي حساسية"),
            ("chief_complaint", "صداع في الرأس", "عندي صداع براسي"),
            ("chief_complaint", "ألم في البطن", "الوجع ببطني"),
            ("severity", "not severe", "الألم مو قوي"),
            ("chief_complaint", "وجع البطن", "الألم ببطني"),
        )
        for field, value, evidence in cases:
            with self.subTest(field=field, evidence=evidence):
                result = grounding_evidence(self.update(field, value), evidence)
                expected = "structured_numeric" if field == "duration" and value == "2 days" else "canonical"
                self.assertEqual(result.classification, expected)
                self.assertIsNotNone(result.evidence_span)
                self.assertEqual(evidence[result.evidence_span.start:result.evidence_span.end], result.evidence_text)

    def test_ckb_unicode_morphology_and_span(self):
        self.assertEqual(normalize_grounding_text("دوو\u200c ڕۆژە؛ کەم"), "دوو ڕۆژە كەم")
        cases = (
            ("chief_complaint", "headache", "سەرێشەکەم هەیە"),
            ("duration", "2 days", "دوو ڕۆژە"),
            ("severity", "severe", "ئازارەکە زۆر توندە"),
            ("location", "chest", "لە سنگم ئازار هەیە"),
            ("current_medications", ["paracetamol"], "پاراسیتامۆل بەکاردەهێنم"),
            ("allergies", ["penicillin"], "هەستیاریی پنسلینم هەیە"),
            ("allergies", ["پنسلین"], "هەستیاریی پنسلینم هەیە"),
            ("duration", "دوو ڕۆژ", "دوو روژه"),
            ("chief_complaint", "سەرێژ", "سه‌ریشم هه‌یه"),
            ("chief_complaint", "سەرئێشە", "سەرم دەئێشێ"),
            ("duration", "یەک هەفتە", "یەک هەفتەیە"),
            ("chief_complaint", "ناڕەحەتی لە سک", "لە سکمە"),
            ("chief_complaint", "ئازاری سک", "لە سکمە"),
            ("severity", "سووک", "سووکە"),
        )
        for field, value, evidence in cases:
            with self.subTest(field=field):
                result = grounding_evidence(self.update(field, value), evidence)
                expected = "structured_numeric" if field == "duration" and value == "2 days" else "canonical"
                self.assertEqual(result.classification, expected)
                self.assertIsNotNone(result.evidence_span)

    def test_vague_negated_family_and_unknown_drug_do_not_overclaim(self):
        rejected = (
            ("duration", "2 days", "صارلي فترة"),
            ("symptoms", ["headache"], "ما عندي صداع"),
            ("symptoms", ["headache"], "امي عندها صداع"),
            ("current_medications", ["metformin"], "اخذ دوا اسمه ميتافور مجهول"),
            ("symptoms", ["headache"], "دایکم سەرێشەی هەیە"),
        )
        for field, value, evidence in rejected:
            with self.subTest(field=field, evidence=evidence):
                self.assertEqual(
                    grounding_classification(self.update(field, value), evidence),
                    "unsupported",
                )

    def test_aliases_require_token_boundaries(self):
        self.assertEqual(
            grounding_classification(self.update("location", "head"), "سەرمەشقی وانەکە"),
            "unsupported",
        )


class PhaseEClinicianReviewTests(SimpleTestCase):
    def _export_rows(self, directory):
        path = Path(directory) / "review.csv"
        export_review_csv(path)
        with path.open(encoding="utf-8", newline="") as handle:
            return path, list(csv.DictReader(handle))

    def test_export_tracks_qualification_and_language_competence(self):
        with TemporaryDirectory() as directory:
            _, rows = self._export_rows(directory)
        self.assertEqual(len(rows), 56)
        self.assertTrue(all("reviewer_qualification" in row for row in rows))
        self.assertTrue(all("reviewer_language_competence" in row for row in rows))

    def test_reviewed_disposition_requires_qualification_and_rule_language(self):
        with TemporaryDirectory() as directory:
            path, rows = self._export_rows(directory)
            row = rows[0]
            row.update({
                "disposition": "approved",
                "reviewer": "reviewer-001",
                "reviewer_role": "clinician",
                "reviewer_qualification": "licensed physician",
                "reviewer_language_competence": "ckb",
                "review_date": "2026-08-15",
            })
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ReviewValidationError):
                import_review_csv(path)
            row["reviewer_language_competence"] = row["language"]
            row["reviewer_qualification"] = ""
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ReviewValidationError):
                import_review_csv(path)
