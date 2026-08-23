"""AI Intake Phase F grounding and deterministic question-target tests."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.ai_intake.services.completeness import (
    projected_question_target_plan,
    question_target_plan,
)
from apps.ai_intake.services.semantic_validation import grounding_evidence


class PhaseFGroundingTests(SimpleTestCase):
    @staticmethod
    def update(field, value, *, certainty="explicit"):
        return SimpleNamespace(field=field, value=value, certainty=certainty)

    def assert_grounded(self, field, value, evidence, classification=None):
        result = grounding_evidence(self.update(field, value), evidence)
        self.assertNotEqual(result.classification, "unsupported")
        if classification:
            self.assertEqual(result.classification, classification)
        self.assertIsNotNone(result.evidence_span)
        return result

    def test_iraqi_structured_numeric_duration(self):
        cases = (
            ("1 day", "صارلي يوم"),
            ("2 days", "صارلي يومين"),
            ("3 days", "صارلي ثلاث ايام"),
            ("2 weeks", "من اسبوعين"),
            ("1 month", "صارله شهر"),
        )
        for value, evidence in cases:
            with self.subTest(evidence=evidence):
                self.assert_grounded(
                    "duration", value, evidence, "structured_numeric"
                )

    def test_vague_duration_never_becomes_exact(self):
        for evidence in ("من كم يوم", "من زمان", "صارلي فترة"):
            with self.subTest(evidence=evidence):
                result = grounding_evidence(
                    self.update("duration", "3 days"), evidence
                )
                self.assertEqual(result.classification, "unsupported")

    def test_iraqi_onset_and_duration_remain_field_scoped(self):
        self.assert_grounded("onset", "yesterday", "بلش البارحة")
        self.assertEqual(
            grounding_evidence(
                self.update("duration", "1 day"), "بلش البارحة"
            ).classification,
            "unsupported",
        )

    def test_iraqi_symptom_severity_and_location(self):
        cases = (
            ("symptoms", ["vomiting"], "دا أرجع من الصبح"),
            ("symptoms", ["cough"], "عندي كحة"),
            ("symptoms", ["fatigue"], "حيل تعبان"),
            ("severity", "moderate", "الوجع متوسط"),
            ("location", "throat", "الوجع بحلقي"),
        )
        for field, value, evidence in cases:
            with self.subTest(field=field, evidence=evidence):
                self.assert_grounded(field, value, evidence)

    def test_v5_complaint_and_duration_variants(self):
        cases = (
            ("chief_complaint", "back pain", "my back aches"),
            ("symptoms", ["abdominal pain"], "بطني يؤلمني"),
            ("chief_complaint", "throat pain", "گەرووم دەئێشێ"),
            ("chief_complaint", "ئازاری گەروو", "گەرووم دەئێشێ"),
            ("chief_complaint", "سک دەئێشێ", "سکم دەئێشێ"),
            ("duration", "3 days", "لمدة ثلاثة أيام"),
            ("duration", "2 weeks", "دوو هەفتەیە"),
            ("duration", "1 month", "صارلي one month"),
            ("allergies", ["none"], "هەستیاریم نییە"),
        )
        for field, value, evidence in cases:
            with self.subTest(field=field, evidence=evidence):
                self.assert_grounded(field, value, evidence)

    def test_correction_uses_latest_explicit_clause(self):
        cases = (
            ("duration", "3 days", "لا مو يومين، ثلاث ايام"),
            ("duration", "1 month", "مو يوم واحد، صارلي شهر"),
            ("location", "back", "لا مو بصدري، بظهري"),
            ("duration", "1 month", "مانگێکە، نەک یەک ڕۆژ"),
        )
        for field, value, evidence in cases:
            with self.subTest(evidence=evidence):
                self.assert_grounded(field, value, evidence, "patient_correction")

    def test_ckb_normalized_negation_and_family_context_reject(self):
        rejected = (
            ("symptoms", ["headache"], "نییە سەرێشە"),
            ("chief_complaint", "headache", "دایکم سەرێشەی هەیە"),
            ("allergies", ["penicillin"], "دایکم هەستیاریی پنسلینی هەیە"),
        )
        for field, value, evidence in rejected:
            with self.subTest(evidence=evidence):
                self.assertEqual(
                    grounding_evidence(
                        self.update(field, value), evidence
                    ).classification,
                    "unsupported",
                )

    def test_ckb_unicode_clitics_and_mixed_drug(self):
        cases = (
            ("duration", "2 days", "دوو\u200cڕۆژە"),
            ("symptoms", ["headache", "nausea"], "سەرێشەم و دڵتێکچوونم هەیە"),
            ("current_medications", ["metformin"], "Metformin بەکاردەهێنم"),
            ("location", "back", "پشتم دەئێشێ"),
        )
        for field, value, evidence in cases:
            with self.subTest(field=field, evidence=evidence):
                self.assert_grounded(field, value, evidence)

    def test_empty_values_and_adverse_effect_are_not_facts(self):
        self.assertEqual(
            grounding_evidence(
                self.update("current_medications", []), "هیچ وردەکارییەک نییە"
            ).classification,
            "unsupported",
        )
        self.assertEqual(
            grounding_evidence(
                self.update("allergies", ["penicillin"]),
                "البنسلين يضوج معدتي",
            ).classification,
            "unsupported",
        )

    def test_safe_patient_occurrence_after_family_occurrence_is_used(self):
        result = self.assert_grounded(
            "symptoms", ["headache"], "امي عندها صداع، واني عندي صداع"
        )
        self.assertGreaterEqual(result.evidence_span.start, 20)


class PhaseFQuestionTargetTests(SimpleTestCase):
    @staticmethod
    def session(metadata=None, *, status="active", suggested=None):
        return SimpleNamespace(
            field_metadata=metadata or {},
            question_count=0,
            status=status,
            language="en",
            suggested_relevant_fields=suggested or [],
        )

    def test_first_required_field_is_deterministic(self):
        plan = question_target_plan(self.session())
        self.assertEqual(plan.preferred_next_field, "chief_complaint")
        self.assertIn("chief_complaint", plan.allowed_next_fields)

    def test_completed_and_optional_fields_excluded_before_blockers(self):
        metadata = {
            "chief_complaint": {"status": "answered"},
            "location": {"status": "missing"},
        }
        plan = question_target_plan(
            self.session(metadata, suggested=["localized_symptom"])
        )
        self.assertNotIn("chief_complaint", plan.allowed_next_fields)
        self.assertNotEqual(plan.preferred_next_field, "location")
        self.assertIn("symptoms", plan.allowed_next_fields)

    def test_uncertain_blocking_field_remains_valid_clarification(self):
        metadata = {
            "chief_complaint": {"status": "answered"},
            "symptoms": {"status": "uncertain"},
        }
        plan = question_target_plan(self.session(metadata))
        self.assertIn("symptoms", plan.allowed_next_fields)

    def test_projected_updates_remove_resolved_field_and_timing_pair(self):
        updates = [
            self.update("chief_complaint", "headache"),
            self.update("symptoms", ["headache"]),
            self.update("duration", "2 days"),
        ]
        plan = projected_question_target_plan(self.session(), updates, [], [])
        self.assertNotIn("chief_complaint", plan.allowed_next_fields)
        self.assertNotIn("symptoms", plan.allowed_next_fields)
        self.assertNotIn("onset", plan.allowed_next_fields)
        self.assertNotIn("duration", plan.allowed_next_fields)
        self.assertEqual(plan.preferred_next_field, "severity")

    @staticmethod
    def update(field, value, *, certainty="explicit"):
        return SimpleNamespace(field=field, value=value, certainty=certainty)

    def test_review_and_emergency_have_no_question_target(self):
        complete = {
            "chief_complaint": {"status": "answered"},
            "symptoms": {"status": "answered"},
            "duration": {"status": "answered"},
            "severity": {"status": "answered"},
            "past_medical_history": {"status": "unknown"},
            "current_medications": {"status": "unknown"},
            "allergies": {"status": "unknown"},
        }
        self.assertIsNone(
            question_target_plan(self.session(complete)).preferred_next_field
        )
        emergency = self.session(status="emergency_stopped")
        self.assertEqual(question_target_plan(emergency).allowed_next_fields, [])
