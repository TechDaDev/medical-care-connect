"""Patient Phase A dashboard contract, aggregation, and permission tests."""

from datetime import date, timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.ai_intake.models import AIIntakeSession, IntakeSessionStatus
from apps.consultations.models import Consultation, ConsultationStatus
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import MedicalRecordDraft
from apps.messaging.models import ConsultationMessage, MessageReadReceipt
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


class PatientDashboardPhaseATests(TestCase):
    endpoint = "/api/patients/me/dashboard/"

    @classmethod
    def setUpTestData(cls):
        cls.specialty = Specialty.objects.create(
            name="Dashboard Specialty",
            slug="dashboard-specialty",
        )
        cls.patient_user = cls._user(
            "dashboard-patient@example.test",
            UserRole.PATIENT,
        )
        cls.patient = PatientProfile.objects.create(user=cls.patient_user)
        cls.patient_user.first_name = "Patient"
        cls.patient_user.last_name = "Example"
        cls.patient_user.phone_number = "0000000000"
        cls.patient_user.save(
            update_fields=["first_name", "last_name", "phone_number"]
        )
        cls.patient.date_of_birth = date(1990, 1, 1)
        cls.patient.address = "Completed"
        cls.patient.emergency_contact_name = "Contact"
        cls.patient.emergency_contact_phone = "0000000001"
        cls.patient.blood_type = "a_positive"
        cls.patient.notes = ""
        cls.patient.save()

        cls.other_patient_user = cls._user(
            "other-patient@example.test",
            UserRole.PATIENT,
        )
        cls.other_patient = PatientProfile.objects.create(
            user=cls.other_patient_user
        )
        cls.doctor_user = cls._user(
            "dashboard-doctor@example.test",
            UserRole.DOCTOR,
        )
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user,
            specialty=cls.specialty,
            license_number="DASHBOARD-LICENSE",
        )

    @staticmethod
    def _user(email, role):
        return User.objects.create_user(
            email=email,
            password="test-only-password",
            role=role,
            first_name="Test",
            last_name="User",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.patient_user)

    def _consultation(self, consultation_status):
        return Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            specialty=self.specialty,
            status=consultation_status,
        )

    def _response(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def test_exact_contract_and_generated_at(self):
        consultation = self._consultation(
            ConsultationStatus.AWAITING_PATIENT_RESPONSE
        )
        ConsultationMessage.objects.create(
            consultation=consultation,
            sender=self.doctor_user,
            content="not returned",
        )
        Notification.objects.create(
            recipient=self.patient_user,
            notification_type=NotificationType.STATUS_CHANGE,
            title="Safe title",
            body="Safe body",
            consultation=consultation,
        )

        response = self._response()
        data = response.data

        self.assertEqual(
            set(data),
            {
                "consultations",
                "attention",
                "messages",
                "notifications",
                "profile",
                "recent_consultations",
                "generated_at",
            },
        )
        self.assertEqual(
            set(data["consultations"]),
            {
                "total",
                "active",
                "awaiting_patient",
                "awaiting_doctor",
                "intake_in_progress",
                "doctor_review",
                "follow_up_required",
                "physical_visit_required",
                "emergency_escalated",
                "completed",
                "cancelled",
            },
        )
        self.assertEqual(set(data["attention"]), {"total", "items"})
        self.assertEqual(
            set(data["attention"]["items"][0]),
            {
                "type",
                "consultation_id",
                "title_key",
                "description_key",
                "count",
                "severity",
                "created_at",
                "action_path",
            },
        )
        self.assertEqual(
            set(data["messages"]),
            {"unread_total", "recent_threads"},
        )
        self.assertEqual(
            set(data["messages"]["recent_threads"][0]),
            {
                "consultation_id",
                "doctor_name",
                "specialty_name",
                "unread_count",
                "last_message_at",
            },
        )
        self.assertEqual(
            set(data["notifications"]),
            {"unread_total", "recent"},
        )
        self.assertEqual(
            set(data["notifications"]["recent"][0]),
            {
                "id",
                "notification_type",
                "title",
                "body",
                "is_read",
                "created_at",
                "consultation_id",
            },
        )
        self.assertEqual(
            set(data["profile"]),
            {
                "completion_percent",
                "missing_fields",
                "emergency_contact_complete",
                "basic_health_complete",
            },
        )
        self.assertEqual(
            set(data["recent_consultations"][0]),
            {
                "id",
                "status",
                "doctor_name",
                "specialty_name",
                "created_at",
                "updated_at",
                "unread_messages",
                "needs_patient_action",
                "has_medical_record",
            },
        )
        self.assertIsNotNone(
            timezone.datetime.fromisoformat(response.json()["generated_at"])
        )
        self.assertNotIn("content", data["messages"]["recent_threads"][0])
        self.assertNotIn("description", data["recent_consultations"][0])

    def test_consultation_counts_cover_patient_workflow(self):
        expected = {
            ConsultationStatus.SUBMITTED: "active",
            ConsultationStatus.AWAITING_PATIENT_RESPONSE: "awaiting_patient",
            ConsultationStatus.AWAITING_DOCTOR_RESPONSE: "awaiting_doctor",
            ConsultationStatus.INTAKE_IN_PROGRESS: "intake_in_progress",
            ConsultationStatus.DOCTOR_REVIEW: "doctor_review",
            ConsultationStatus.FOLLOW_UP_REQUIRED: "follow_up_required",
            ConsultationStatus.PHYSICAL_VISIT_REQUIRED: "physical_visit_required",
            ConsultationStatus.EMERGENCY_ESCALATED: "emergency_escalated",
            ConsultationStatus.COMPLETED: "completed",
            ConsultationStatus.CANCELLED: "cancelled",
        }
        for consultation_status in expected:
            self._consultation(consultation_status)
        Consultation.objects.create(
            patient=self.other_patient,
            doctor=self.doctor,
            specialty=self.specialty,
            status=ConsultationStatus.COMPLETED,
        )

        counts = self._response().data["consultations"]

        self.assertEqual(counts["total"], len(expected))
        self.assertEqual(counts["active"], 8)
        for key in expected.values():
            if key != "active":
                self.assertEqual(counts[key], 1)

    def test_attention_is_authoritative_and_has_no_duplicates(self):
        consultations = {
            consultation_status: self._consultation(consultation_status)
            for consultation_status in (
                ConsultationStatus.AWAITING_PATIENT_RESPONSE,
                ConsultationStatus.FOLLOW_UP_REQUIRED,
                ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
                ConsultationStatus.EMERGENCY_ESCALATED,
                ConsultationStatus.INTAKE_IN_PROGRESS,
                ConsultationStatus.DOCTOR_REVIEW,
            )
        }
        AIIntakeSession.objects.create(
            consultation=consultations[ConsultationStatus.INTAKE_IN_PROGRESS],
            status=IntakeSessionStatus.IN_PROGRESS,
        )
        ConsultationMessage.objects.create(
            consultation=consultations[
                ConsultationStatus.AWAITING_PATIENT_RESPONSE
            ],
            sender=self.doctor_user,
            content="not returned",
        )

        items = self._response().data["attention"]["items"]
        item_types = [item["type"] for item in items]

        self.assertCountEqual(
            item_types,
            [
                ConsultationStatus.AWAITING_PATIENT_RESPONSE,
                ConsultationStatus.FOLLOW_UP_REQUIRED,
                ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
                ConsultationStatus.EMERGENCY_ESCALATED,
                "intake_incomplete",
                "unread_messages",
            ],
        )
        identities = [
            (item["type"], item["consultation_id"]) for item in items
        ]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertNotIn(ConsultationStatus.DOCTOR_REVIEW, item_types)

    def test_completed_intake_is_not_patient_attention(self):
        consultation = self._consultation(
            ConsultationStatus.INTAKE_IN_PROGRESS
        )
        AIIntakeSession.objects.create(
            consultation=consultation,
            status=IntakeSessionStatus.CONFIRMED,
        )

        self.assertEqual(self._response().data["attention"]["items"], [])

    def test_messages_are_grouped_read_filtered_ordered_and_content_free(self):
        older = self._consultation(ConsultationStatus.ACCEPTED)
        newer = self._consultation(ConsultationStatus.ACCEPTED)
        read_message = ConsultationMessage.objects.create(
            consultation=older,
            sender=self.doctor_user,
            content="read and hidden",
        )
        MessageReadReceipt.objects.create(
            message=read_message,
            user=self.patient_user,
        )
        ConsultationMessage.objects.create(
            consultation=older,
            sender=self.patient_user,
            content="outgoing and hidden",
        )
        first_unread = ConsultationMessage.objects.create(
            consultation=older,
            sender=self.doctor_user,
            content="first hidden",
        )
        second_unread = ConsultationMessage.objects.create(
            consultation=older,
            sender=self.doctor_user,
            content="second hidden",
        )
        latest_unread = ConsultationMessage.objects.create(
            consultation=newer,
            sender=self.doctor_user,
            content="latest hidden",
        )
        now = timezone.now()
        ConsultationMessage.objects.filter(
            id__in=[first_unread.id, second_unread.id]
        ).update(sent_at=now - timedelta(hours=1))
        ConsultationMessage.objects.filter(id=latest_unread.id).update(
            sent_at=now
        )

        messages = self._response().data["messages"]

        self.assertEqual(messages["unread_total"], 3)
        threads = messages["recent_threads"]
        older_thread = next(
            item for item in threads if item["consultation_id"] == older.id
        )
        self.assertEqual(older_thread["unread_count"], 2)
        self.assertEqual(threads[0]["consultation_id"], older.id)
        self.assertTrue(all("content" not in thread for thread in threads))

    def test_recent_threads_and_consultations_are_limited_to_five(self):
        for _ in range(7):
            consultation = self._consultation(ConsultationStatus.ACCEPTED)
            ConsultationMessage.objects.create(
                consultation=consultation,
                sender=self.doctor_user,
                content="not returned",
            )

        data = self._response().data

        self.assertEqual(len(data["messages"]["recent_threads"]), 5)
        self.assertEqual(len(data["recent_consultations"]), 5)

    def test_notifications_are_scoped_limited_and_safe(self):
        for index in range(7):
            Notification.objects.create(
                recipient=self.patient_user,
                notification_type=NotificationType.STATUS_CHANGE,
                title=f"Title {index}",
                body="Safe body",
                is_read=index == 0,
            )
        Notification.objects.create(
            recipient=self.other_patient_user,
            notification_type=NotificationType.STATUS_CHANGE,
            title="Other patient",
            body="Not returned",
        )

        notifications = self._response().data["notifications"]

        self.assertEqual(notifications["unread_total"], 6)
        self.assertEqual(len(notifications["recent"]), 5)
        self.assertNotIn(
            "Other patient",
            [item["title"] for item in notifications["recent"]],
        )
        self.assertTrue(
            all(
                set(item)
                == {
                    "id",
                    "notification_type",
                    "title",
                    "body",
                    "is_read",
                    "created_at",
                    "consultation_id",
                }
                for item in notifications["recent"]
            )
        )

    def test_profile_completion_uses_required_fields_not_notes(self):
        complete = self._response().data["profile"]
        self.assertEqual(complete["completion_percent"], 100)
        self.assertEqual(complete["missing_fields"], [])
        self.assertTrue(complete["emergency_contact_complete"])
        self.assertTrue(complete["basic_health_complete"])

        self.patient.address = ""
        self.patient.emergency_contact_phone = ""
        self.patient.blood_type = "unknown"
        self.patient.notes = "Optional notes do not affect completion"
        self.patient.save()

        incomplete = self._response().data["profile"]
        self.assertEqual(incomplete["completion_percent"], 70)
        self.assertCountEqual(
            incomplete["missing_fields"],
            ["address", "emergency_contact_phone", "blood_type"],
        )
        self.assertFalse(incomplete["emergency_contact_complete"])
        self.assertFalse(incomplete["basic_health_complete"])
        self.assertNotIn("notes", incomplete["missing_fields"])

    def test_recent_consultation_flags_and_safe_fields(self):
        consultation = self._consultation(
            ConsultationStatus.FOLLOW_UP_REQUIRED
        )
        ConsultationMessage.objects.create(
            consultation=consultation,
            sender=self.doctor_user,
            content="not returned",
        )
        MedicalRecordDraft.objects.create(consultation=consultation)

        recent = self._response().data["recent_consultations"][0]

        self.assertEqual(recent["unread_messages"], 1)
        self.assertTrue(recent["needs_patient_action"])
        self.assertTrue(recent["has_medical_record"])
        self.assertNotIn("description", recent)

    def test_dashboard_query_count_is_bounded(self):
        for _ in range(8):
            consultation = self._consultation(
                ConsultationStatus.AWAITING_PATIENT_RESPONSE
            )
            ConsultationMessage.objects.create(
                consultation=consultation,
                sender=self.doctor_user,
                content="not returned",
            )
        self.client.force_authenticate(
            User.objects.get(pk=self.patient_user.pk)
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.endpoint)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(queries), 9)

    def test_patient_allowed_other_roles_and_anonymous_denied(self):
        self.assertEqual(
            self.client.get(self.endpoint).status_code,
            status.HTTP_200_OK,
        )
        for role in (
            UserRole.DOCTOR,
            UserRole.COORDINATOR,
            UserRole.ADMINISTRATOR,
        ):
            user = self._user(f"{role}@example.test", role)
            self.client.force_authenticate(user)
            with self.subTest(role=role):
                self.assertEqual(
                    self.client.get(self.endpoint).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(self.endpoint).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
