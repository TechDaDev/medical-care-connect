"""Tests for messaging and notification Phase 5 features.

Hard limit: 10 tests total.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.doctors.models import DoctorProfile
from apps.messaging.models import ConsultationMessage, DoctorInternalNote, MessageReadReceipt, MessageType
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


class Phase5MessagingTests(APITestCase):
    """Tests for messaging, internal notes, and notifications."""

    @classmethod
    def setUpTestData(cls):
        cls.patient_user = User.objects.create_user(
            email="patient@test.com", password="testpass123",
            role=UserRole.PATIENT, first_name="Test", last_name="Patient",
        )
        cls.doctor_user = User.objects.create_user(
            email="doctor@test.com", password="testpass123",
            role=UserRole.DOCTOR, first_name="Test", last_name="Doctor",
        )
        cls.other_user = User.objects.create_user(
            email="other@test.com", password="testpass123",
            role=UserRole.PATIENT,
        )
        cls.specialty = Specialty.objects.create(name="TestCardiology", slug="test-cardiology")
        cls.patient_profile = PatientProfile.objects.create(
            user=cls.patient_user, date_of_birth="1990-01-01",
        )
        cls.doctor_profile = DoctorProfile.objects.create(
            user=cls.doctor_user, specialty=cls.specialty,
            professional_title="Cardiologist", license_number="LIC-MSG-001",
            consultation_fee=100, is_approved=True,
            is_accepting_consultations=True,
        )
        cls.consultation = Consultation.objects.create(
            patient=cls.patient_profile,
            doctor=cls.doctor_profile,
            specialty=cls.specialty,
            status=ConsultationStatus.SUBMITTED,
        )

    # ── Helper ──────────────────────────────────────────────────────────

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_01_send_and_list_messages(self):
        """Patient sends a message; doctor lists messages (gets marked read)."""
        self._auth(self.patient_user)
        resp = self.client.post(
            f"/api/messaging/{self.consultation.id}/messages/",
            {"content": "Hello Doctor"},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        msg_id = resp.data["id"]

        # Doctor lists — gets message, it's auto-marked read
        self._auth(self.doctor_user)
        resp = self.client.get(f"/api/messaging/{self.consultation.id}/messages/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["content"], "Hello Doctor")

        # Verify read receipt exists for doctor
        self.assertTrue(
            MessageReadReceipt.objects.filter(
                message_id=msg_id, user=self.doctor_user
            ).exists()
        )

    def test_02_block_messaging_when_completed(self):
        """Should not allow messaging when consultation is completed."""
        self.consultation.status = ConsultationStatus.COMPLETED
        self.consultation.save(update_fields=["status"])

        self._auth(self.patient_user)
        resp = self.client.post(
            f"/api/messaging/{self.consultation.id}/messages/",
            {"content": "Hello after completed"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_03_unread_message_counts(self):
        """Patient sees unread count for a consultation with new messages."""
        # Doctor sends a message
        ConsultationMessage.objects.create(
            consultation=self.consultation,
            sender=self.doctor_user,
            content="From doctor",
        )
        self._auth(self.patient_user)
        resp = self.client.get(
            f"/api/messaging/{self.consultation.id}/messages/unread-count/"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["unread_count"], 1)

    def test_04_unread_counts_all(self):
        """Patient can get unread counts for all consultations."""
        ConsultationMessage.objects.create(
            consultation=self.consultation,
            sender=self.doctor_user,
            content="Unread message",
        )
        self._auth(self.patient_user)
        resp = self.client.get("/api/messaging/unread-counts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 1)

    def test_05_mark_messages_read(self):
        """Explicitly mark a message as read."""
        msg = ConsultationMessage.objects.create(
            consultation=self.consultation,
            sender=self.doctor_user,
            content="Read me",
        )
        self._auth(self.patient_user)
        resp = self.client.post(
            f"/api/messaging/{self.consultation.id}/messages/read/",
            {"message_ids": [str(msg.id)]},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            MessageReadReceipt.objects.filter(message=msg, user=self.patient_user).exists()
        )

    def test_06_access_denied_non_participant(self):
        """A non-participant cannot access messages."""
        self._auth(self.other_user)
        resp = self.client.get(f"/api/messaging/{self.consultation.id}/messages/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_07_doctor_internal_notes_crud(self):
        """Doctor can create, list, and delete internal notes."""
        self._auth(self.doctor_user)
        # Create
        resp = self.client.post(
            f"/api/messaging/{self.consultation.id}/internal-notes/",
            {"content": "Patient seems anxious"},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        note_id = resp.data["id"]

        # List
        resp = self.client.get(
            f"/api/messaging/{self.consultation.id}/internal-notes/"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

        # Delete
        resp = self.client.delete(
            f"/api/messaging/{self.consultation.id}/internal-notes/{note_id}/"
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_08_patient_cannot_access_internal_notes(self):
        """Patient cannot list or create internal notes."""
        self._auth(self.patient_user)
        resp = self.client.get(
            f"/api/messaging/{self.consultation.id}/internal-notes/"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_09_notifications_created_and_read(self):
        """System creates notifications; user can list and mark read."""
        # Create a notification manually
        Notification.objects.create(
            recipient=self.patient_user,
            notification_type=NotificationType.NEW_MESSAGE,
            title="Test Notification",
            body="You have a new message.",
            consultation=self.consultation,
        )

        self._auth(self.patient_user)
        # List notifications
        resp = self.client.get("/api/notifications/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["title"], "Test Notification")
        self.assertFalse(resp.data[0]["is_read"])

        # Mark read
        resp = self.client.post("/api/notifications/read/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["marked_read"], 1)

    def test_10_unread_notification_count(self):
        """User can get unread notification count."""
        Notification.objects.create(
            recipient=self.patient_user,
            notification_type=NotificationType.NEW_MESSAGE,
            title="Unread",
        )
        self._auth(self.patient_user)
        resp = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["unread_count"], 1)
