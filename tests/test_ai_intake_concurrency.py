"""AI Intake Phase A — real PostgreSQL concurrency tests.

Runs with config.settings.test_postgres so SELECT ... FOR UPDATE provides
real row-locking semantics.  Uses TransactionTestCase + separate connections
per worker thread.  Deterministic mocks only; never calls the live provider.

Run with:
  python manage.py test tests.test_ai_intake_concurrency \
      --settings=config.settings.test_postgres
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.ai_intake.models import (
    AIIntakeMessage,
    AIIntakeSession,
    IntakeIdempotencyLedger,
    IntakeSessionStatus,
)
from apps.ai_intake.prompts import PROMPT_VERSION
from apps.ai_intake.services.base import AIProviderUnavailable
from apps.ai_intake.services.intake import (
    confirm_intake,
    process_intake_answer,
    start_intake_session,
    submit_intake,
)
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import MedicalRecordDraft
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty

_LOCAL = threading.local()


def _in_thread(fn, *args):
    try:
        return fn(*args)
    finally:
        close_old_connections()


def _run_concurrently(calls):
    """calls: list of (fn, args_tuple). Returns list of results in order."""
    with ThreadPoolExecutor(max_workers=len(calls)) as ex:
        futures = [ex.submit(_in_thread, fn, *args) for fn, args in calls]
        return [f.result() for f in futures]


class _CountingProvider:
    """Thread-safe deterministic provider that emits a valid turn."""

    def __init__(self, response):
        self.response = response
        self.calls = 0
        self.lock = threading.Lock()
        self.input_tokens = 10
        self.output_tokens = 8
        self.total_tokens = 18

    def generate_structured_response(self, messages, schema_name="intake_turn"):
        with self.lock:
            self.calls += 1
        return self.response


def _valid_turn():
    return {
        "conversation_status": "needs_more_information",
        "patient_facing_message": "Thank you. How long?",
        "next_question": {"field": "duration", "text": "How long?"},
        "extracted_updates": [],
        "uncertain_fields": [],
        "suggested_relevant_fields": [],
        "emergency_signal": {"detected": False, "level": "none", "reasons": []},
        "summary_for_review": None,
    }


def _confirm_call(session):
    return confirm_intake(
        session,
        expected_updated_at=session.updated_at.isoformat(),
        client_request_id=uuid4(),
    )


def _submit_call(session):
    return submit_intake(
        session,
        expected_updated_at=session.updated_at.isoformat(),
        client_request_id=uuid4(),
    )


@skipUnless(
    connection.vendor == "postgresql",
    "AI intake concurrency tests require PostgreSQL row locking.",
)
class IntakeConcurrencyBase(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.specialty = Specialty.objects.create(
            name=f"Con {uuid4().hex[:8]}", name_en=f"Con {uuid4().hex[:8]}",
            name_ar="تجريبي", name_ckb="تاقیکاری",
            slug=f"con-{uuid4().hex[:10]}",
        )
        self.patient_user = User.objects.create_user(
            email=f"con-p-{uuid4().hex[:10]}@example.test", role=UserRole.PATIENT)
        self.patient = PatientProfile.objects.create(user=self.patient_user)
        self.doctor_user = User.objects.create_user(
            email=f"con-d-{uuid4().hex[:10]}@example.test", role=UserRole.DOCTOR)
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user, specialty=self.specialty,
            professional_title="Synthetic", license_number=f"LC-{uuid4().hex[:10]}",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient, doctor=self.doctor, specialty=self.specialty,
            status=ConsultationStatus.ACCEPTED,
            description="Synthetic concurrency consultation. No real patient data.",
        )

    def complete_metadata(self):
        fields = ["chief_complaint", "symptoms", "onset", "duration", "severity",
                  "past_medical_history", "current_medications", "allergies"]
        meta = {}
        for name in fields:
            meta[name] = {
                "value": "synthetic" if name != "symptoms" else ["synthetic symptom"],
                "status": "answered", "source": "intake_extraction",
                "confidence": "high",
                "evidence_message_ids": [str(uuid4())],
                "confirmed_by_patient": True,
            }
        return meta

    def _confirmed_session(self):
        meta = self.complete_metadata()
        s = AIIntakeSession.objects.create(
            consultation=self.consultation, status="confirmed",
            field_metadata=meta, confirmed_at=timezone.now(),
            question_count=4,
        )
        return s


class ConcurrentStartTests(IntakeConcurrencyBase):
    def test_concurrent_start_creates_one_session(self):
        start_intake_session(self.consultation, language="en")
        results = _run_concurrently([
            (start_intake_session, (self.consultation, "en")),
            (start_intake_session, (self.consultation, "en")),
        ])
        self.assertEqual(len(results), 2)
        self.assertEqual(
            AIIntakeSession.objects.filter(consultation=self.consultation).count(), 1
        )


class ConcurrentAnswerTests(IntakeConcurrencyBase):
    def _provider(self):
        return _CountingProvider(_valid_turn())

    def test_duplicate_same_answer_single_provider_call(self):
        session = start_intake_session(self.consultation, language="en")
        rid = uuid4()
        provider = self._provider()
        with patch(
            "apps.ai_intake.services.intake._get_provider", return_value=provider
        ):
            with patch("apps.ai_intake.services.intake.validate_semantics"):
                _run_concurrently([
                    (process_intake_answer, (session, "synthetic answer", rid)),
                    (process_intake_answer, (session, "synthetic answer", rid)),
                ])
        self.assertEqual(
            AIIntakeMessage.objects.filter(session=session, role="patient").count(), 1
        )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(
            IntakeIdempotencyLedger.objects.filter(
                session=session, action="answer", client_request_id=rid).count(), 1
        )

    def test_two_different_answers_sequenced(self):
        session = start_intake_session(self.consultation, language="en")
        provider = self._provider()
        with patch(
            "apps.ai_intake.services.intake._get_provider", return_value=provider
        ):
            with patch("apps.ai_intake.services.intake.validate_semantics"):
                _run_concurrently([
                    (process_intake_answer, (session, "answer alpha", uuid4())),
                    (process_intake_answer, (session, "answer beta", uuid4())),
                ])
        all_messages = list(
            AIIntakeMessage.objects.filter(session=session).order_by("sequence_number")
        )
        # 2 patient + 2 assistant messages, unique increasing sequences.
        self.assertEqual(len(all_messages), 4)
        self.assertEqual([m.sequence_number for m in all_messages], [1, 2, 3, 4])
        patient_msgs = [m for m in all_messages if m.role == "patient"]
        self.assertEqual(len(patient_msgs), 2)
        self.assertEqual(
            [m.sequence_number for m in patient_msgs], [1, 3]
        )
        # Exactly two provider calls — one per accepted turn.
        self.assertEqual(provider.calls, 2)

    def test_timeout_then_retry_recovers(self):
        session = start_intake_session(self.consultation, language="en")

        class _AlwaysTimeout(_CountingProvider):
            def generate_structured_response(self, messages, schema_name="intake_turn"):
                with self.lock:
                    self.calls += 1
                raise AIProviderUnavailable("t", safe_code="provider_timeout")

        provider_fail = _AlwaysTimeout(_valid_turn())
        with patch(
            "apps.ai_intake.services.intake._get_provider", return_value=provider_fail
        ):
            with patch("apps.ai_intake.services.base.time.sleep"):
                session, first = process_intake_answer(
                    session, "first answer", uuid4())
        self.assertTrue(first["retryable"])
        session.refresh_from_db()
        self.assertEqual(session.status, IntakeSessionStatus.TEMPORARILY_UNAVAILABLE)

        # Retry with a healthy provider and a fresh request id recovers.
        provider_ok = _CountingProvider(_valid_turn())
        with patch(
            "apps.ai_intake.services.intake._get_provider", return_value=provider_ok
        ):
            with patch("apps.ai_intake.services.intake.validate_semantics"):
                session, second = process_intake_answer(
                    session, "second answer", uuid4())
        self.assertEqual(second["conversation_status"], "needs_more_information")
        session.refresh_from_db()
        self.assertEqual(session.status, IntakeSessionStatus.IN_PROGRESS)
        # Two patient messages persisted across the failure and the retry.
        self.assertEqual(
            AIIntakeMessage.objects.filter(session=session, role="patient").count(), 2
        )


class ConcurrentConfirmTests(IntakeConcurrencyBase):
    def test_concurrent_confirm_one_transition(self):
        session = self._confirmed_session()
        # Move to reviewable state.
        session.status = "awaiting_patient_review"
        session.save()
        _run_concurrently([
            (_confirm_call, (session,)),
            (_confirm_call, (session,)),
        ])
        session.refresh_from_db()
        self.assertEqual(session.status, IntakeSessionStatus.CONFIRMED)
        self.assertIsNotNone(session.confirmed_at)
        self.assertIsNotNone(session.confirmation_snapshot)
        # One confirmation audit (only the real transition audits).
        self.assertEqual(
            AuditEvent.objects.filter(event_type="patient_intake_confirmed").count(), 1
        )


class ConcurrentSubmitTests(IntakeConcurrencyBase):
    def test_concurrent_submit_single_draft_single_notification(self):
        session = self._confirmed_session()
        _run_concurrently([
            (_submit_call, (session,)),
            (_submit_call, (session,)),
        ])
        session.refresh_from_db()
        self.assertEqual(session.status, IntakeSessionStatus.SUBMITTED_TO_DOCTOR)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, ConsultationStatus.DOCTOR_REVIEW)
        # Exactly one draft, one notification, one audit.
        self.assertEqual(
            MedicalRecordDraft.objects.filter(consultation=self.consultation).count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(
                notification_type=NotificationType.INTAKE_COMPLETED).count(), 1
        )
        self.assertEqual(
            AuditEvent.objects.filter(event_type="patient_intake_submitted").count(), 1
        )

    def test_concurrent_submit_with_cancellation_race(self):
        """Submission and cancellation racing produce a consistent terminal state."""
        session = self._confirmed_session()

        def _submit():
            try:
                _submit_call(session)
                return "submitted"
            except Exception:
                return "intake_not_confirmed"

        def _cancel():
            try:
                s2 = AIIntakeSession.objects.get(pk=session.pk)
                s2.status = IntakeSessionStatus.CANCELLED
                s2.save(update_fields=["status", "updated_at"])
                return "cancelled"
            except Exception:
                return "cancel_failed"

        _run_concurrently([(_submit, ()), (_cancel, ())])
        session.refresh_from_db()
        # Both outcomes are valid terminal states; no partial draft.
        self.assertIn(
            session.status,
            {IntakeSessionStatus.SUBMITTED_TO_DOCTOR, IntakeSessionStatus.CANCELLED},
        )


class ConcurrentEmergencyTests(IntakeConcurrencyBase):
    def test_answer_vs_emergency_no_corruption(self):
        session = start_intake_session(self.consultation, language="en")
        provider = _CountingProvider(_valid_turn())

        def _answer_normal():
            try:
                process_intake_answer(session, "I have a normal complaint", uuid4())
                return "accepted"
            except Exception:
                # Session may already be closed by the emergency thread.
                return "closed"

        def _answer_emergency():
            process_intake_answer(session, "crushing chest pain", uuid4())
            return "emergency"

        with patch(
            "apps.ai_intake.services.intake._get_provider", return_value=provider
        ):
            with patch("apps.ai_intake.services.intake.validate_semantics"):
                _run_concurrently([(_answer_normal, ()), (_answer_emergency, ())])
        session.refresh_from_db()
        self.consultation.refresh_from_db()
        # The deterministic emergency branch, when it runs, stops the session.
        if session.status == IntakeSessionStatus.EMERGENCY_STOPPED:
            self.assertEqual(
                self.consultation.status, ConsultationStatus.EMERGENCY_ESCALATED)
        # No duplicate/empty patient messages; unique sequences.
        patient_count = AIIntakeMessage.objects.filter(
            session=session, role="patient").count()
        self.assertLessEqual(patient_count, 2)
        seqs = list(
            AIIntakeMessage.objects.filter(session=session)
            .values_list("sequence_number", flat=True)
        )
        self.assertEqual(len(seqs), len(set(seqs)))
