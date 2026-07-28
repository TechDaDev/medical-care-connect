"""Doctor Phase A: access, dashboard, availability, and accepting status."""

from datetime import time
from threading import Barrier, Lock, Thread
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus, Priority
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorAvailability, DoctorProfile, Weekday
from apps.messaging.models import (
    ConsultationMessage,
    DoctorInternalNote,
    MessageReadReceipt,
)
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.reviews.models import ConsultationReview, ReviewStatus
from apps.specialties.models import Specialty


ACCESS_KEYS = {
    "state",
    "can_access_dashboard",
    "can_manage_availability",
    "can_accept_consultations",
    "can_edit_profile",
    "reason_code",
    "approval_status",
    "is_approved",
    "is_accepting_consultations",
    "profile_id",
    "updated_at",
    "next_path",
}


def create_user(email, role=UserRole.DOCTOR, *, active=True):
    return User.objects.create_user(
        email=email,
        password="phase-a-password",
        first_name="Phase",
        last_name="Tester",
        phone_number="+9647500000000",
        role=role,
        is_active=active,
    )


def create_doctor(email, approval_status, *, approved=None, active=True):
    user = create_user(email, active=active)
    specialty_code = email.split("@")[0]
    if approved is None:
        approved = approval_status == DoctorProfile.ApprovalStatus.APPROVED
    profile = DoctorProfile.objects.create(
        user=user,
        specialty=Specialty.objects.create(
            name=f"Specialty {specialty_code}",
            name_en=f"Specialty {specialty_code}",
            slug=f"specialty-{specialty_code}",
        ),
        professional_title="Consultant",
        workplace_name="Medical Care Connect",
        qualifications="Board certified",
        biography="Professional biography",
        license_number=f"PHASE-A-{specialty_code}",
        years_of_experience=8,
        consultation_fee="20.00",
        languages=["en", "ar"],
        estimated_response_minutes=45,
        approval_status=approval_status,
        is_approved=approved,
        is_accepting_consultations=False,
    )
    return user, profile


class DoctorAccessStateTests(TestCase):
    endpoint = "/api/doctors/me/access-state/"

    def setUp(self):
        self.client = APIClient()

    def fetch(self, user):
        self.client.force_authenticate(user)
        return self.client.get(self.endpoint)

    def test_all_access_states_and_safe_exact_contract(self):
        cases = (
            (
                DoctorProfile.ApprovalStatus.APPROVED,
                "approved",
                None,
                "/app/doctor",
            ),
            (
                DoctorProfile.ApprovalStatus.PENDING,
                "pending",
                "application_pending",
                "/app/doctor/pending-approval",
            ),
            (
                DoctorProfile.ApprovalStatus.REJECTED,
                "rejected",
                "application_rejected",
                "/app/doctor/application-rejected",
            ),
            (
                DoctorProfile.ApprovalStatus.SUSPENDED,
                "suspended",
                "account_suspended",
                "/app/doctor/suspended",
            ),
        )
        for index, (approval, state_name, reason, next_path) in enumerate(cases):
            user, _profile = create_doctor(f"state{index}@example.com", approval)
            response = self.fetch(user)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(set(response.data), ACCESS_KEYS)
            self.assertEqual(response.data["state"], state_name)
            self.assertEqual(response.data["reason_code"], reason)
            self.assertEqual(response.data["next_path"], next_path)
            self.assertNotIn("approval_note", response.data)
            self.assertNotIn("license_number", response.data)

    def test_missing_profile_and_inactive_state(self):
        missing = create_user("missing@example.com")
        response = self.fetch(missing)
        self.assertEqual(response.data["state"], "missing_profile")
        self.assertEqual(response.data["reason_code"], "doctor_profile_missing")

        inactive, _profile = create_doctor(
            "inactive@example.com",
            DoctorProfile.ApprovalStatus.APPROVED,
            active=False,
        )
        response = self.fetch(inactive)
        self.assertEqual(response.data["state"], "inactive")
        self.assertEqual(response.data["reason_code"], "account_inactive")

    def test_non_doctor_roles_and_anonymous_denied(self):
        for role in (
            UserRole.PATIENT,
            UserRole.COORDINATOR,
            UserRole.ADMINISTRATOR,
        ):
            response = self.fetch(create_user(f"{role}@example.com", role))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(self.endpoint).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_access_state_query_bound(self):
        user, _profile = create_doctor(
            "queries@example.com", DoctorProfile.ApprovalStatus.APPROVED
        )
        user = User.objects.get(pk=user.pk)
        self.client.force_authenticate(user)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 1)


class DoctorDashboardPhaseATests(TestCase):
    endpoint = "/api/doctors/me/dashboard/"

    @classmethod
    def setUpTestData(cls):
        cls.doctor_user, cls.doctor = create_doctor(
            "dashboard-doctor@example.com",
            DoctorProfile.ApprovalStatus.APPROVED,
        )
        cls.other_user, cls.other_doctor = create_doctor(
            "other-doctor@example.com",
            DoctorProfile.ApprovalStatus.APPROVED,
        )
        cls.patient_user = create_user(
            "dashboard-patient@example.com", UserRole.PATIENT
        )
        cls.patient = PatientProfile.objects.create(user=cls.patient_user)
        cls.other_patient_user = create_user(
            "other-patient@example.com", UserRole.PATIENT
        )
        cls.other_patient = PatientProfile.objects.create(
            user=cls.other_patient_user
        )
        cls.consultations = {}
        for consultation_status, _label in ConsultationStatus.choices:
            cls.consultations[consultation_status] = Consultation.objects.create(
                patient=cls.patient,
                doctor=cls.doctor,
                specialty=cls.doctor.specialty,
                status=consultation_status,
                priority=(
                    Priority.URGENT
                    if consultation_status == ConsultationStatus.SUBMITTED
                    else Priority.MEDIUM
                ),
            )
        cls.other_consultation = Consultation.objects.create(
            patient=cls.other_patient,
            doctor=cls.other_doctor,
            specialty=cls.other_doctor.specialty,
            status=ConsultationStatus.SUBMITTED,
        )

        unread = ConsultationMessage.objects.create(
            consultation=cls.consultations[ConsultationStatus.SUBMITTED],
            sender=cls.patient_user,
            content="private patient message",
        )
        read = ConsultationMessage.objects.create(
            consultation=cls.consultations[ConsultationStatus.SUBMITTED],
            sender=cls.patient_user,
            content="already read",
        )
        MessageReadReceipt.objects.create(message=read, user=cls.doctor_user)
        ConsultationMessage.objects.create(
            consultation=cls.other_consultation,
            sender=cls.other_patient_user,
            content="other doctor private message",
        )
        DoctorInternalNote.objects.create(
            consultation=cls.consultations[ConsultationStatus.SUBMITTED],
            author=cls.doctor_user,
            content="internal clinical note",
        )
        cls.unread = unread

        Notification.objects.create(
            recipient=cls.doctor_user,
            notification_type=NotificationType.NEW_CONSULTATION,
            title="New consultation",
            body="Safe notification",
            consultation=cls.consultations[ConsultationStatus.SUBMITTED],
        )
        Notification.objects.create(
            recipient=cls.other_user,
            notification_type=NotificationType.NEW_MESSAGE,
            title="Other",
            body="Other doctor",
        )
        ConsultationReview.objects.create(
            consultation=cls.consultations[ConsultationStatus.COMPLETED],
            reviewer=cls.patient,
            rating=5,
            is_anonymous=True,
            has_response=False,
            status=ReviewStatus.PUBLISHED,
        )
        ConsultationReview.objects.create(
            consultation=cls.consultations[ConsultationStatus.CANCELLED],
            reviewer=cls.patient,
            rating=1,
            status=ReviewStatus.HIDDEN,
        )
        DoctorAvailability.objects.create(
            doctor=cls.doctor,
            day_of_week=Weekday.MONDAY,
            start_time=time(9),
            end_time=time(12),
            is_active=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.doctor_user)

    def test_exact_contract_counts_scoping_and_privacy(self):
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(
            set(data),
            {
                "access",
                "profile",
                "consultations",
                "attention",
                "messages",
                "notifications",
                "reviews",
                "availability",
                "recent_consultations",
                "generated_at",
            },
        )
        self.assertEqual(set(data["access"]), ACCESS_KEYS)
        self.assertEqual(
            set(data["consultations"]),
            {
                "total_active",
                "submitted",
                "accepted",
                "intake_in_progress",
                "intake_completed",
                "doctor_review",
                "awaiting_patient",
                "awaiting_doctor",
                "under_review",
                "follow_up_required",
                "physical_visit_required",
                "transferred",
                "emergency_escalated",
                "completed",
                "cancelled",
            },
        )
        for consultation_status, _label in ConsultationStatus.choices:
            if consultation_status == ConsultationStatus.DRAFT:
                continue
            key = {
                ConsultationStatus.AWAITING_PATIENT_RESPONSE: "awaiting_patient",
                ConsultationStatus.AWAITING_DOCTOR_RESPONSE: "awaiting_doctor",
            }.get(consultation_status, consultation_status)
            self.assertEqual(data["consultations"][key], 1)

        self.assertEqual(data["messages"]["unread_total"], 1)
        self.assertEqual(len(data["messages"]["recent_threads"]), 1)
        self.assertNotIn("content", data["messages"]["recent_threads"][0])
        self.assertNotIn("private patient message", str(data))
        self.assertNotIn("internal clinical note", str(data))
        self.assertEqual(data["notifications"]["unread_total"], 1)
        self.assertEqual(len(data["notifications"]["recent"]), 1)
        self.assertTrue(
            data["notifications"]["recent"][0]["action_path"].startswith(
                "/app/doctor/"
            )
        )
        self.assertEqual(data["reviews"]["total_reviews"], 1)
        self.assertEqual(data["reviews"]["average_rating"], 5)
        self.assertEqual(data["reviews"]["awaiting_response"], 1)
        self.assertNotIn("reviewer", data["reviews"]["recent"][0])
        self.assertEqual(data["availability"]["active_slot_count"], 1)
        self.assertLessEqual(len(data["recent_consultations"]), 5)

    def test_attention_is_authoritative_unique_and_excludes_awaiting_patient(self):
        data = self.client.get(self.endpoint).data
        types = [item["type"] for item in data["attention"]["items"]]
        self.assertEqual(len(types), len(set(types)))
        for expected in (
            "new_consultation",
            "intake_ready",
            "awaiting_doctor_response",
            "urgent_consultation",
            "emergency_escalation",
            "unread_messages",
            "review_response",
        ):
            self.assertIn(expected, types)
        self.assertNotIn("awaiting_patient", types)
        for item in data["attention"]["items"]:
            self.assertTrue(item["action_path"].startswith("/app/"))

    def test_dashboard_query_count_is_fixed(self):
        fresh_user = User.objects.get(pk=self.doctor_user.pk)
        self.client.force_authenticate(fresh_user)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            len(queries),
            10,
            [query["sql"] for query in queries.captured_queries],
        )

        for index in range(12):
            Consultation.objects.create(
                patient=self.patient,
                doctor=self.doctor,
                specialty=self.doctor.specialty,
                status=ConsultationStatus.ACCEPTED,
            )
        fresh_user = User.objects.get(pk=self.doctor_user.pk)
        self.client.force_authenticate(fresh_user)
        with CaptureQueriesContext(connection) as larger_queries:
            response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(larger_queries), len(queries))

    def test_operational_permissions(self):
        for index, approval in enumerate(
            (
                DoctorProfile.ApprovalStatus.PENDING,
                DoctorProfile.ApprovalStatus.REJECTED,
                DoctorProfile.ApprovalStatus.SUSPENDED,
            )
        ):
            user, _profile = create_doctor(f"blocked{index}@example.com", approval)
            self.client.force_authenticate(user)
            response = self.client.get(self.endpoint)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        for role in (
            UserRole.PATIENT,
            UserRole.COORDINATOR,
            UserRole.ADMINISTRATOR,
        ):
            self.client.force_authenticate(
                create_user(f"blocked-{role}@example.com", role)
            )
            self.assertEqual(
                self.client.get(self.endpoint).status_code,
                status.HTTP_403_FORBIDDEN,
            )


class DoctorAvailabilityPhaseATests(TestCase):
    list_endpoint = "/api/doctors/me/availability/"
    toggle_endpoint = "/api/doctors/me/availability-status/"

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = create_doctor(
            "availability@example.com",
            DoctorProfile.ApprovalStatus.APPROVED,
        )
        self.other_user, self.other_profile = create_doctor(
            "availability-other@example.com",
            DoctorProfile.ApprovalStatus.APPROVED,
        )
        self.client.force_authenticate(self.user)

    def create_slot(self, **overrides):
        values = {
            "doctor": self.profile,
            "day_of_week": Weekday.MONDAY,
            "start_time": time(9),
            "end_time": time(12),
            "is_active": True,
        }
        values.update(overrides)
        return DoctorAvailability.objects.create(**values)

    def test_list_is_owned_safe_deterministic_and_bounded(self):
        self.create_slot()
        self.create_slot(
            doctor=self.other_profile,
            day_of_week=Weekday.TUESDAY,
        )
        fresh_user = User.objects.get(pk=self.user.pk)
        self.client.force_authenticate(fresh_user)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.list_endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data),
            {
                "timezone",
                "is_accepting_consultations",
                "can_manage",
                "slots",
                "generated_at",
            },
        )
        self.assertEqual(len(response.data["slots"]), 1)
        self.assertEqual(
            set(response.data["slots"][0]),
            {
                "id",
                "day_of_week",
                "start_time",
                "end_time",
                "is_active",
                "updated_at",
                "version",
            },
        )
        self.assertEqual(len(queries), 2)

    def test_create_validation_conflicts_and_audit(self):
        valid = {
            "day_of_week": "monday",
            "start_time": "09:00",
            "end_time": "12:00",
            "is_active": True,
        }
        response = self.client.post(self.list_endpoint, valid, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="doctor_availability_created",
                actor_id=str(self.user.id),
            ).exists()
        )
        self.assertNotIn("content", str(AuditEvent.objects.latest("created_at").metadata))

        duplicate = self.client.post(self.list_endpoint, valid, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(duplicate.data["code"], "duplicate_availability")

        overlap = self.client.post(
            self.list_endpoint,
            {**valid, "start_time": "10:00", "end_time": "13:00"},
            format="json",
        )
        self.assertEqual(overlap.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(overlap.data["code"], "availability_overlap")

        equal = self.client.post(
            self.list_endpoint,
            {**valid, "day_of_week": "tuesday", "start_time": "09:00", "end_time": "09:00"},
            format="json",
        )
        self.assertEqual(equal.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("invalid_time_range", str(equal.data))

        overnight = self.client.post(
            self.list_endpoint,
            {**valid, "day_of_week": "tuesday", "start_time": "22:00", "end_time": "06:00"},
            format="json",
        )
        self.assertEqual(overnight.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unsupported_cross_midnight", str(overnight.data))

        protected = self.client.post(
            self.list_endpoint,
            {**valid, "doctor": str(self.other_profile.id)},
            format="json",
        )
        self.assertEqual(protected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("field_not_allowed", str(protected.data))

    def test_update_stale_overlap_ownership_and_delete(self):
        slot = self.create_slot()
        other = self.create_slot(
            doctor=self.other_profile,
            day_of_week=Weekday.WEDNESDAY,
        )
        detail = f"{self.list_endpoint}{slot.id}/"
        response = self.client.patch(
            detail,
            {
                "start_time": "08:00",
                "expected_updated_at": slot.updated_at.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="doctor_availability_updated",
                target_id=str(slot.id),
            ).exists()
        )

        stale_value = response.data["updated_at"]
        DoctorAvailability.objects.filter(pk=slot.pk).update(
            updated_at=timezone.now()
        )
        stale = self.client.patch(
            detail,
            {
                "end_time": "13:00",
                "expected_updated_at": stale_value,
            },
            format="json",
        )
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale.data["code"], "stale_availability")

        self.assertEqual(
            self.client.patch(
                f"{self.list_endpoint}{other.id}/",
                {"start_time": "08:00"},
                format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        deleted = self.client.delete(detail)
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="doctor_availability_deleted",
                target_id=str(slot.id),
            ).exists()
        )
        again = self.client.delete(detail)
        self.assertEqual(again.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(again.data["code"], "availability_not_found")

    def test_accepting_status_is_atomic_idempotent_and_authoritative(self):
        original = self.profile.updated_at.isoformat()
        enabled = self.client.patch(
            self.toggle_endpoint,
            {
                "is_accepting_consultations": True,
                "expected_updated_at": original,
            },
            format="json",
        )
        self.assertEqual(enabled.status_code, status.HTTP_200_OK)
        self.assertTrue(enabled.data["changed"])
        self.assertTrue(enabled.data["is_accepting_consultations"])
        self.assertIn("active_slot_count", enabled.data)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="doctor_accepting_status_updated"
            ).exists()
        )

        repeated = self.client.patch(
            self.toggle_endpoint,
            {"is_accepting_consultations": True},
            format="json",
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertFalse(repeated.data["changed"])
        self.assertEqual(
            repeated.data["reason"], "accepting_status_unchanged"
        )

        stale = self.client.patch(
            self.toggle_endpoint,
            {
                "is_accepting_consultations": False,
                "expected_updated_at": original,
            },
            format="json",
        )
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale.data["code"], "stale_accepting_status")

    def test_blocked_doctors_and_foreign_roles_denied(self):
        for index, approval in enumerate(
            (
                DoctorProfile.ApprovalStatus.PENDING,
                DoctorProfile.ApprovalStatus.REJECTED,
                DoctorProfile.ApprovalStatus.SUSPENDED,
            )
        ):
            user, _profile = create_doctor(f"availability-blocked{index}@example.com", approval)
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.get(self.list_endpoint).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.client.patch(
                    self.toggle_endpoint,
                    {"is_accepting_consultations": True},
                    format="json",
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row-lock test")
class DoctorAvailabilityConcurrencyTests(TransactionTestCase):
    reset_sequences = False

    def test_concurrent_overlapping_create_keeps_one_slot(self):
        user, profile = create_doctor(
            "availability-concurrency@example.com",
            DoctorProfile.ApprovalStatus.APPROVED,
        )
        barrier = Barrier(2)
        result_lock = Lock()
        results = []

        def create(start_time, end_time):
            close_old_connections()
            thread_user = User.objects.get(pk=user.pk)
            client = APIClient()
            client.force_authenticate(thread_user)
            barrier.wait()
            response = client.post(
                "/api/doctors/me/availability/",
                {
                    "day_of_week": "monday",
                    "start_time": start_time,
                    "end_time": end_time,
                    "is_active": True,
                },
                format="json",
            )
            with result_lock:
                results.append(response.status_code)
            close_old_connections()

        threads = [
            Thread(target=create, args=("09:00", "12:00")),
            Thread(target=create, args=("10:00", "13:00")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(
            DoctorAvailability.objects.filter(doctor=profile).count(),
            1,
        )
