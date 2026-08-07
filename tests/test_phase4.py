"""Tests for Phase 4: AI intake and medical record drafts."""

import json
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.ai_intake.models import AIIntakeSession, AIIntakeMessage
from apps.ai_intake.services.emergency import screen_patient_input
from apps.consultations.models import Consultation, ConsultationStatus
from apps.doctors.models import DoctorProfile
from apps.patients.models import PatientProfile
from apps.medical_records.models import MedicalRecordDraft
from apps.specialties.models import Specialty


def _jpost(client, url: str, data: dict, **kwargs):
    return client.post(
        url, json.dumps(data), content_type="application/json", **kwargs,
    )


def _jpatch(client, url: str, data: dict, **kwargs):
    return client.patch(
        url, json.dumps(data), content_type="application/json", **kwargs,
    )


def _login(client, email: str, password: str) -> str | None:
    resp = _jpost(
        client, reverse("accounts:login"),
        {"email": email, "password": password},
    )
    if resp.status_code != 200:
        return None
    token = resp.cookies.get("mcc_access")
    token_value = token.value if token else None
    client.cookies.clear()
    return token_value


class EmergencyScreeningTests(TestCase):
    """Deterministic keyword emergency screening (no AI cost)."""

    def test_suicide_keyword_detected(self):
        result = screen_patient_input("I want to kill myself")
        self.assertTrue(result["detected"])
        self.assertEqual(result["level"], "emergency")

    def test_chest_pain_detected(self):
        result = screen_patient_input("crushing chest pain")
        self.assertTrue(result["detected"])
        self.assertEqual(result["level"], "emergency")

    def test_breathing_difficulty_detected(self):
        result = screen_patient_input("can't breathe")
        self.assertTrue(result["detected"])
        self.assertEqual(result["level"], "urgent")

    def test_normal_input_no_emergency(self):
        result = screen_patient_input("I have a mild headache for 3 days")
        self.assertFalse(result["detected"])
        self.assertEqual(result["level"], "none")


class MockAIResponse:
    """Simulate a successful AI turn."""

    class Choice:
        class Message:
            def __init__(self, content):
                self.content = content
                self.refusal = None

        def __init__(self, content, finish_reason="stop"):
            self.message = self.Message(content)
            self.finish_reason = finish_reason

    class Usage:
        prompt_tokens = 50
        completion_tokens = 30
        total_tokens = 80

    def __init__(self, content, finish_reason="stop"):
        self.choices = [self.Choice(content, finish_reason)]
        self.usage = self.Usage()


@override_settings(
    AI_INTAKE_ENABLED=True,
    DEEPSEEK_API_KEY="test-only-key",
    DEEPSEEK_MODEL="test-only-model",
)
class IntakeFlowTests(TestCase):
    """End-to-end intake flow with mocked AI."""

    def setUp(self):
        self.spec = Specialty.objects.create(name="General", slug="general")
        self.patient_user = User.objects.create_user(
            email="patient@test.com", password="pass123",
            first_name="Test", last_name="Patient", role=UserRole.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user, date_of_birth="1990-01-01",
        )
        self.doc_user = User.objects.create_user(
            email="doctor@test.com", password="pass123",
            first_name="Test", last_name="Doctor", role=UserRole.DOCTOR,
        )
        self.doc = DoctorProfile.objects.create(
            user=self.doc_user, specialty=self.spec,
            professional_title="GP", consultation_fee=50,
            is_approved=True, license_number="LIC-TEST",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient, doctor=self.doc, specialty=self.spec,
            status=ConsultationStatus.ACCEPTED,
        )
        self.token = _login(self.client, "patient@test.com", "pass123")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _mock_ai(self, status="needs_more_information", question="Any other symptoms?"):
        """Return a mock AI response dict in the Phase A schema format."""
        msg = question or "Your information has been recorded."
        return json.dumps({
            "conversation_status": status,
            "patient_facing_message": msg,
            "next_question": (
                {"field": "duration", "text": question}
                if question else None
            ),
            "extracted_updates": [],
            "uncertain_fields": [],
            "suggested_relevant_fields": [],
            "emergency_signal": {"detected": False, "level": "none", "reasons": []},
            "summary_for_review": None,
        })

    @override_settings(DEEPSEEK_MODEL=None)
    def test_start_intake_creates_session(self):
        url = reverse("consultations:intake-start", args=[self.consultation.id])
        resp = _jpost(self.client, url, {"language": "en"}, **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["session_status"], "in_progress")
        session = AIIntakeSession.objects.get(consultation=self.consultation)
        self.assertEqual(session.ai_model, "")

    def test_start_intake_requires_patient_ownership(self):
        other_user = User.objects.create_user(
            email="other@test.com", password="pass123",
            first_name="Other", last_name="User", role=UserRole.PATIENT,
        )
        PatientProfile.objects.create(user=other_user, date_of_birth="1990-01-01")
        token = _login(self.client, "other@test.com", "pass123")
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        url = reverse("consultations:intake-start", args=[self.consultation.id])
        resp = _jpost(self.client, url, {"language": "en"}, **headers)
        self.assertEqual(resp.status_code, 404)

    @patch("apps.ai_intake.services.deepseek.OpenAI")
    def test_answer_intake(self, mock_openai):
        # Create session first
        url = reverse("consultations:intake-start", args=[self.consultation.id])
        resp = _jpost(self.client, url, {"language": "en"}, **self.headers)
        session_id = resp.json()["session_id"]

        # Mock AI provider
        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create.return_value = MockAIResponse(
            self._mock_ai()
        )

        url = reverse("intake:intake-answer", args=[session_id])
        resp = _jpost(self.client, url, {"answer": "I have a headache"}, **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["session_status"], "in_progress")
        self.assertEqual(data["question_count"], 1)

    @patch("apps.ai_intake.services.deepseek.OpenAI")
    def test_intake_confirm_and_submit_generates_draft(self, mock_openai):
        """Phase A: intake completes at the backend gate, then patient confirms
        and submits before a draft is generated."""
        # Start session
        url = reverse("consultations:intake-start", args=[self.consultation.id])
        resp = _jpost(self.client, url, {"language": "en"}, **self.headers)
        session_id = resp.json()["session_id"]
        session = AIIntakeSession.objects.get(pk=session_id)

        # Seed deterministic complete metadata (Phase A backend gate authority).
        fields = ["chief_complaint", "symptoms", "onset", "duration", "severity",
                  "past_medical_history", "current_medications", "allergies"]
        metadata = {}
        for name in fields:
            metadata[name] = {
                "value": "headache" if name == "chief_complaint" else (
                    ["head pain"] if name == "symptoms" else "synthetic"),
                "status": "answered",
                "source": "patient_message",
                "confidence": "high",
                "evidence_message_ids": [],
                "confirmed_by_patient": False,
            }
        session.field_metadata = metadata
        session.status = "awaiting_patient_review"
        session.save()

        # Review is allowed by the deterministic completeness gate.
        review_url = reverse("intake:intake-review", args=[session_id])
        rv = self.client.get(review_url, **self.headers)
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(rv.json()["can_confirm"])

        # No draft exists before confirmation/submission.
        self.assertFalse(MedicalRecordDraft.objects.filter(
            consultation=self.consultation
        ).exists())

        # Confirm.
        session.refresh_from_db()
        confirm_url = reverse("intake:intake-confirm", args=[session_id])
        rc = _jpost(self.client, confirm_url, {
            "expected_updated_at": session.updated_at.isoformat(),
            "confirmation": True,
            "client_request_id": str(uuid4()),
        }, **self.headers)
        self.assertEqual(rc.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, "confirmed")

        # Submit → one draft is generated.
        submit_url = reverse("intake:intake-submit", args=[session_id])
        rs = _jpost(self.client, submit_url, {
            "expected_updated_at": session.updated_at.isoformat(),
            "client_request_id": str(uuid4()),
        }, **self.headers)
        self.assertEqual(rs.status_code, 200)
        self.assertEqual(rs.json()["consultation_status"], "doctor_review")
        self.assertTrue(MedicalRecordDraft.objects.filter(
            consultation=self.consultation
        ).exists())

    def test_emergency_answer_blocks_intake(self):
        url = reverse("consultations:intake-start", args=[self.consultation.id])
        resp = _jpost(self.client, url, {"language": "en"}, **self.headers)
        session_id = resp.json()["session_id"]

        url = reverse("intake:intake-answer", args=[session_id])
        resp = _jpost(self.client, url,
                      {"answer": "I have crushing chest pain"}, **self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["session_status"], "emergency_stopped")
        self.assertTrue(data["emergency_detected"])
        self.assertEqual(data["emergency_level"], "emergency")


class MedicalRecordTests(TestCase):
    """Medical record draft CRUD and confirmation."""

    def setUp(self):
        self.spec = Specialty.objects.create(name="General", slug="general")
        self.patient_user = User.objects.create_user(
            email="patient@test.com", password="pass123",
            first_name="Test", last_name="Patient", role=UserRole.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user, date_of_birth="1990-01-01",
        )
        self.doc_user = User.objects.create_user(
            email="doctor@test.com", password="pass123",
            first_name="Test", last_name="Doctor", role=UserRole.DOCTOR,
        )
        self.doc = DoctorProfile.objects.create(
            user=self.doc_user, specialty=self.spec,
            professional_title="GP", consultation_fee=50,
            is_approved=True, license_number="LIC-TEST",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient, doctor=self.doc, specialty=self.spec,
            status=ConsultationStatus.SUBMITTED,
        )
        self.record = MedicalRecordDraft.objects.create(
            consultation=self.consultation,
            chief_complaint="headache",
            symptoms=["head pain"],
        )
        self.patient_token = _login(self.client, "patient@test.com", "pass123")
        self.patient_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.patient_token}"}
        self.doc_token = _login(self.client, "doctor@test.com", "pass123")
        self.doc_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.doc_token}"}

    def test_patient_can_read_record(self):
        url = reverse("records:record-detail", args=[self.record.id])
        resp = self.client.get(url, **self.patient_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["chief_complaint"], "headache")

    def test_patient_cannot_update_record(self):
        url = reverse("records:record-detail", args=[self.record.id])
        resp = _jpatch(self.client, url,
                       {"chief_complaint": "changed"}, **self.patient_headers)
        self.assertEqual(resp.status_code, 403)

    def test_doctor_can_update_record(self):
        url = reverse("records:record-detail", args=[self.record.id])
        resp = _jpatch(self.client, url,
                       {"doctor_notes": "Reviewed"}, **self.doc_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["doctor_notes"], "Reviewed")

    def test_patient_confirms_record(self):
        url = reverse("records:record-confirm", args=[self.record.id])
        resp = _jpost(self.client, url,
                      {"confirmed": True}, **self.patient_headers)
        self.assertEqual(resp.status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "finalized")
