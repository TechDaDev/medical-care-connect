import json
from pathlib import Path
from uuid import uuid4

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import SimpleTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.ai_intake.emergency_rules.registry import ALL_RULES, RULESET_VERSION
from apps.ai_intake.evaluation import EvaluationOptions, EvaluationSafetyError, load_dataset, run_evaluation
from apps.ai_intake.models import AIIntakeMessage, IntakeSessionStatus
from apps.ai_intake.services.emergency import screen_patient_input
from apps.medical_records.models import MedicalRecordDraft
from apps.accounts.models import User, UserRole
from apps.doctors.models import DoctorProfile
from tests.test_ai_intake_phase_a_extended import PhaseAExtendedBase

FIXTURES = Path(__file__).parent / "fixtures"


class EmergencyGovernanceTests(SimpleTestCase):
    def test_all_rules_have_truthful_unreviewed_metadata(self):
        self.assertTrue(ALL_RULES)
        self.assertEqual(RULESET_VERSION, "mcc-emergency-rules-v1")
        self.assertTrue(all(rule.clinician_review_status == "unreviewed" for rule in ALL_RULES))
        self.assertTrue(all(rule.version and rule.code and rule.language for rule in ALL_RULES))

    def test_synthetic_multilingual_matrix(self):
        payload = json.loads((FIXTURES / "ai_intake_emergency_cases.json").read_text())
        self.assertTrue(payload["synthetic"])
        for case in payload["cases"]:
            with self.subTest(case=case["id"]):
                result = screen_patient_input(case["text"])
                self.assertEqual(result["detected"], case["detected"])
                self.assertEqual(result["level"], case["level"])
                self.assertEqual(result["reasons"], case["rule_codes"])


class DoctorIntakePhaseBContractTests(PhaseAExtendedBase):
    def test_complete_projection_is_safe_bounded_and_record_link_uses_record_id(self):
        session = self._start()
        session.status = IntakeSessionStatus.SUBMITTED_TO_DOCTOR
        session.emergency_reasons = ["chest_pain"]
        patient_message = AIIntakeMessage.objects.create(
            session=session, role="patient", content="Synthetic headache",
            sequence_number=50,
        )
        AIIntakeMessage.objects.create(
            session=session, role="system", content="hidden-system-prompt",
            sequence_number=51,
        )
        session.field_metadata = {
            "chief_complaint": {
                "value": "Synthetic headache", "status": "answered",
                "source": "patient_correction", "confirmed_by_patient": True,
                "confidence": 0.999,
                "evidence_message_ids": [str(patient_message.id), str(uuid4())],
            },
            "allergies": {"status": "unknown", "source": "patient_message"},
            "social_history": {"status": "declined", "source": "patient_message"},
        }
        session.save()
        record = MedicalRecordDraft.objects.create(consultation=self.consultation)
        client = APIClient()
        client.force_authenticate(self.doctor_user)
        url = f"/api/consultations/{self.consultation.id}/doctor-intake/"
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 4)
        self.assertEqual(response.data["patient"]["display_name"], self.patient_user.full_name)
        self.assertEqual(response.data["medical_record"]["id"], str(record.id))
        self.assertIn(str(record.id), response.data["medical_record"]["action_path"])
        self.assertEqual(response.data["unknown_fields"], ["allergies"])
        self.assertEqual(response.data["declined_fields"], ["social_history"])
        field = next(
            item for item in response.data["structured_fields"]
            if item["field"] == "chief_complaint"
        )
        self.assertEqual(field["evidence_message_ids"], [str(patient_message.id)])
        body = str(response.data)
        self.assertNotIn("hidden-system-prompt", body)
        self.assertNotIn("confidence", body)
        self.assertNotIn("ai_provider", body)

    def test_transferred_pending_and_suspended_doctors_cannot_read_intake(self):
        session = self._start()
        url = f"/api/consultations/{self.consultation.id}/doctor-intake/"
        other_user = User.objects.create_user(
            email=f"phase-b-transfer-{uuid4().hex}@example.test", role=UserRole.DOCTOR
        )
        other = DoctorProfile.objects.create(
            user=other_user, specialty=self.specialty,
            license_number=f"SYN-{uuid4().hex}", is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        self.consultation.doctor = other
        self.consultation.save(update_fields=["doctor", "updated_at"])
        client = APIClient()
        client.force_authenticate(self.doctor_user)
        self.assertEqual(client.get(url).status_code, 404)

        for approval_status in (
            DoctorProfile.ApprovalStatus.PENDING,
            DoctorProfile.ApprovalStatus.SUSPENDED,
        ):
            other.approval_status = approval_status
            other.is_approved = False
            other.save(update_fields=["approval_status", "is_approved", "updated_at"])
            client.force_authenticate(other_user)
            self.assertEqual(client.get(url).status_code, 403)
        self.assertTrue(session.pk)


class EvaluationHarnessTests(SimpleTestCase):
    def setUp(self):
        self.dataset_path = FIXTURES / "ai_intake_evaluation_cases.json"
        self.dataset = load_dataset(self.dataset_path)

    def test_mock_is_default_and_report_is_sanitized(self):
        report = run_evaluation(self.dataset, EvaluationOptions(max_cases=8))
        self.assertEqual(report["provider"], "mock")
        self.assertEqual(report["case_count"], 8)
        self.assertEqual(report["metrics"]["prompt_injection_resistance_rate"], 1.0)
        self.assertEqual(report["metrics"]["premature_completion_rejection_rate"], 0.0)
        self.assertEqual(report["metrics"]["emergency_downgrade_rejection_rate"], 0.0)
        body = json.dumps(report)
        self.assertNotIn("API key", body)
        self.assertNotIn("base_url", body)
        self.assertNotIn("system prompt and prescribe", body)

    @override_settings(AI_INTAKE_LIVE_EVAL_ENABLED=True, DEEPSEEK_API_KEY="synthetic-key", DEEPSEEK_MODEL="synthetic-model")
    def test_live_refused_without_explicit_flag(self):
        with self.assertRaises(EvaluationSafetyError):
            run_evaluation(self.dataset, EvaluationOptions(provider="deepseek"))

    @override_settings(AI_INTAKE_LIVE_EVAL_ENABLED=False)
    def test_live_refused_when_disabled(self):
        with self.assertRaises(EvaluationSafetyError):
            run_evaluation(self.dataset, EvaluationOptions(provider="deepseek", allow_live_provider=True))

    def test_non_synthetic_dataset_refused(self):
        with self.assertRaises(EvaluationSafetyError):
            run_evaluation({"synthetic": False, "cases": []}, EvaluationOptions(provider="deepseek", allow_live_provider=True))

    def test_management_command_refuses_live_by_default(self):
        with self.assertRaises(CommandError):
            call_command("evaluate_ai_intake", provider="deepseek", dataset=str(self.dataset_path))
