from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.reviews.models import ConsultationReview, ReviewStatus
from apps.specialties.models import Specialty


class PatientPhaseBTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.specialty = Specialty.objects.create(
            name="Phase B Cardiology",
            name_en="Phase B Cardiology",
            name_ar="طب القلب",
            name_ckb="نەخۆشییەکانی دڵ",
            slug="phase-b-cardiology",
        )
        self.other_specialty = Specialty.objects.create(
            name="Phase B Neurology",
            name_en="Phase B Neurology",
            name_ar="طب الأعصاب",
            name_ckb="نەخۆشییەکانی دەمار",
            slug="phase-b-neurology",
        )
        self.doctor = self._doctor(
            "available@example.test",
            first_name="Ava",
            last_name="Care",
            specialty=self.specialty,
            experience=12,
            fee="75.00",
            response=45,
            languages=["en", "ar"],
            biography="Experienced specialist. " * 20,
            qualifications="Board certified cardiologist",
        )
        self.patient_user = User.objects.create_user(
            email="patient@example.test",
            role=UserRole.PATIENT,
        )
        self.patient = PatientProfile.objects.create(user=self.patient_user)
        self.list_url = reverse("doctors:doctor-list")
        self.detail_url = reverse(
            "doctors:doctor-detail",
            args=[self.doctor.id],
        )
        self.create_url = reverse("consultations:list")

    def _doctor(
        self,
        email,
        *,
        first_name="Doctor",
        last_name="Test",
        specialty=None,
        approved=True,
        approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        active=True,
        accepting=True,
        experience=5,
        fee="50.00",
        response=60,
        languages=None,
        biography="Professional biography",
        qualifications="Medical qualification",
    ):
        user = User.objects.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.DOCTOR,
            is_active=active,
        )
        return DoctorProfile.objects.create(
            user=user,
            specialty=specialty or self.specialty,
            license_number=f"LIC-{uuid4()}",
            professional_title="Consultant",
            workplace_name="Medical Care Clinic",
            qualifications=qualifications,
            biography=biography,
            years_of_experience=experience,
            consultation_fee=Decimal(fee),
            languages=languages or ["en"],
            is_approved=approved,
            approval_status=approval_status,
            is_accepting_consultations=accepting,
            estimated_response_minutes=response,
        )

    def _results(self, **params):
        response = self.client.get(self.list_url, params)
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def _create_payload(self, **overrides):
        payload = {
            "doctor": str(self.doctor.id),
            "description": "Persistent headache and dizziness for several days.",
            "client_request_id": str(uuid4()),
            "expected_doctor_updated_at": self.doctor.updated_at.isoformat(),
        }
        payload.update(overrides)
        return payload

    def _post_as(self, user, payload=None):
        self.client.force_authenticate(user=user)
        return self.client.post(
            self.create_url,
            payload or self._create_payload(),
            format="json",
        )

    def test_public_contract_permissions_safety_and_eligibility(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {"count", "next", "previous", "results"},
        )
        item = response.json()["results"][0]
        self.assertEqual(
            set(item),
            {
                "id",
                "full_name",
                "specialty",
                "professional_title",
                "workplace_name",
                "years_of_experience",
                "consultation_fee",
                "languages",
                "is_accepting_consultations",
                "estimated_response_minutes",
                "average_rating",
                "total_reviews",
                "profile_summary",
                "available_actions",
            },
        )
        self.assertEqual(
            item["consultation_fee"],
            {"amount": "75.00", "currency": "USD"},
        )
        self.assertLessEqual(len(item["profile_summary"]), 240)
        self.assertEqual(
            item["available_actions"],
            ["view", "start_consultation"],
        )
        for private_field in (
            "email",
            "phone_number",
            "license_number",
            "medical_license_document",
            "approval_note",
            "is_approved",
            "approval_status",
        ):
            self.assertNotIn(private_field, item)

        detail = self.client.get(self.detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["unavailable_reason"], None)
        self.assertIn("biography", detail.json())
        self.assertIn("qualifications", detail.json())

        excluded = [
            self._doctor(
                "pending@example.test",
                approved=False,
                approval_status=DoctorProfile.ApprovalStatus.PENDING,
            ),
            self._doctor(
                "rejected@example.test",
                approved=True,
                approval_status=DoctorProfile.ApprovalStatus.REJECTED,
            ),
            self._doctor(
                "suspended@example.test",
                approved=True,
                approval_status=DoctorProfile.ApprovalStatus.SUSPENDED,
            ),
            self._doctor("inactive@example.test", active=False),
        ]
        visible_ids = {entry["id"] for entry in self._results(page_size=50)}
        self.assertIn(str(self.doctor.id), visible_ids)
        self.assertTrue(
            all(str(profile.id) not in visible_ids for profile in excluded)
        )

    def test_filters_search_ordering_pagination_and_localization(self):
        second = self._doctor(
            "second@example.test",
            first_name="Basil",
            last_name="Neuro",
            specialty=self.other_specialty,
            experience=25,
            fee="120.00",
            response=180,
            languages=["ckb"],
            accepting=False,
            qualifications="Neurology fellowship",
        )
        self.assertEqual(
            len(self._results(search="Ava")),
            1,
        )
        self.assertEqual(
            len(self._results(search="Neurology")),
            1,
        )
        self.assertEqual(
            len(self._results(specialty=str(self.specialty.id))),
            1,
        )
        self.assertEqual(len(self._results(language="ckb")), 1)
        self.assertEqual(len(self._results(accepting="true")), 1)
        self.assertEqual(len(self._results(accepting="false")), 1)
        self.assertEqual(len(self._results(min_experience=20)), 1)
        self.assertEqual(len(self._results(min_fee=100, max_fee=130)), 1)
        self.assertEqual(len(self._results(max_response_minutes=60)), 1)
        self.assertEqual(
            self._results(ordering="experience_desc")[0]["id"],
            str(second.id),
        )
        self.assertEqual(
            self._results(ordering="fee_asc")[0]["id"],
            str(self.doctor.id),
        )
        page = self.client.get(
            self.list_url,
            {"page": 2, "page_size": 1},
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["count"], 2)
        self.assertEqual(len(page.json()["results"]), 1)
        oversized = self.client.get(self.list_url, {"page_size": 51})
        self.assertEqual(oversized.status_code, 400)
        arabic = self._results(locale="ar")[0]
        self.assertEqual(arabic["specialty"]["name"], "طب القلب")
        kurdish_detail = self.client.get(
            self.detail_url,
            {"locale": "ckb"},
        )
        self.assertEqual(
            kurdish_detail.json()["specialty"]["name"],
            "نەخۆشییەکانی دڵ",
        )

    def test_rating_aggregation_unavailable_detail_and_query_bounds(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            specialty=self.specialty,
            status=ConsultationStatus.COMPLETED,
        )
        ConsultationReview.objects.create(
            consultation=consultation,
            reviewer=self.patient,
            rating=5,
            status=ReviewStatus.PUBLISHED,
        )
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.list_url)
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 5)
        item = response.json()["results"][0]
        self.assertEqual(item["average_rating"], 5.0)
        self.assertEqual(item["total_reviews"], 1)

        with CaptureQueriesContext(connection) as captured:
            detail = self.client.get(self.detail_url)
            self.assertEqual(detail.status_code, 200)
        self.assertLessEqual(len(captured), 3)

        self.doctor.is_accepting_consultations = False
        self.doctor.save()
        detail = self.client.get(self.detail_url)
        self.assertEqual(
            detail.json()["unavailable_reason"],
            "not_accepting_consultations",
        )
        self.assertEqual(detail.json()["available_actions"], ["view"])

        self.specialty.is_active = False
        self.specialty.save()
        self.assertEqual(self._results(), [])
        detail = self.client.get(self.detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["unavailable_reason"],
            "specialty_inactive",
        )

    def test_create_authoritative_transaction_notification_audit_and_idempotency(self):
        request_id = str(uuid4())
        payload = self._create_payload(
            client_request_id=request_id,
            specialty=str(self.specialty.id),
            description="  Persistent   headache and dizziness for several days.  ",
        )
        first = self._post_as(self.patient_user, payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(
            set(first.json()),
            {
                "id",
                "status",
                "doctor",
                "specialty",
                "created_at",
                "submitted_at",
                "next_path",
            },
        )
        consultation = Consultation.objects.get(id=first.json()["id"])
        self.assertEqual(consultation.specialty, self.doctor.specialty)
        self.assertEqual(
            consultation.description,
            "Persistent headache and dizziness for several days.",
        )
        self.assertEqual(consultation.status, ConsultationStatus.SUBMITTED)
        self.assertIsNotNone(consultation.submitted_at)
        self.assertEqual(
            first.json()["next_path"],
            f"/app/patient/consultations/{consultation.id}",
        )
        self.assertEqual(
            Notification.objects.filter(
                consultation=consultation,
                recipient=self.doctor.user,
                notification_type=NotificationType.NEW_CONSULTATION,
            ).count(),
            1,
        )
        event = AuditEvent.objects.get(
            event_type="patient_consultation_created",
            target_id=str(consultation.id),
        )
        self.assertNotIn("description", event.metadata)
        self.assertNotIn(consultation.description, str(event.metadata))

        second = self._post_as(self.patient_user, payload)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(
            Consultation.objects.filter(
                patient=self.patient,
                client_request_id=request_id,
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(consultation=consultation).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="patient_consultation_created",
                target_id=str(consultation.id),
            ).count(),
            1,
        )

        changed = dict(payload)
        changed["description"] = (
            "Different persistent symptom requiring medical review."
        )
        duplicate = self._post_as(self.patient_user, changed)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["code"], "duplicate_request")

    def test_create_validation_doctor_states_specialty_and_concurrency(self):
        mismatch = self._post_as(
            self.patient_user,
            self._create_payload(specialty=str(self.other_specialty.id)),
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.json()["code"], "specialty_mismatch")
        self.assertEqual(Consultation.objects.count(), 0)

        self.doctor.is_accepting_consultations = False
        self.doctor.save()
        unavailable = self._post_as(self.patient_user)
        self.assertEqual(unavailable.status_code, 409)
        self.assertEqual(unavailable.json()["code"], "doctor_not_accepting")
        self.assertEqual(Consultation.objects.count(), 0)

        self.doctor.is_accepting_consultations = True
        self.doctor.approval_status = DoctorProfile.ApprovalStatus.SUSPENDED
        self.doctor.save()
        suspended = self._post_as(self.patient_user)
        self.assertEqual(suspended.status_code, 400)
        self.assertEqual(
            suspended.json()["code"],
            "doctor_profile_unavailable",
        )

        self.doctor.approval_status = DoctorProfile.ApprovalStatus.APPROVED
        self.doctor.save()
        self.specialty.is_active = False
        self.specialty.save()
        inactive_specialty = self._post_as(self.patient_user)
        self.assertEqual(
            inactive_specialty.status_code,
            409,
            inactive_specialty.json(),
        )
        self.assertEqual(
            inactive_specialty.json()["code"],
            "specialty_inactive",
        )

        self.specialty.is_active = True
        self.specialty.save()
        stale_time = self.doctor.updated_at - timedelta(seconds=1)
        stale = self._post_as(
            self.patient_user,
            self._create_payload(
                expected_doctor_updated_at=stale_time.isoformat(),
            ),
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "doctor_state_changed")
        self.assertEqual(Consultation.objects.count(), 0)

    def test_description_validation_unicode_and_query_bound(self):
        invalid_descriptions = [
            "",
            "   ",
            "too short",
            "a" * 30,
            "x" * 2001,
        ]
        for description in invalid_descriptions:
            response = self._post_as(
                self.patient_user,
                self._create_payload(description=description),
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Consultation.objects.count(), 0)

        arabic = self._post_as(
            self.patient_user,
            self._create_payload(
                description="أعاني من ألم مستمر في الرأس منذ عدة أيام",
            ),
        )
        self.assertEqual(arabic.status_code, 201)
        kurdish = self._post_as(
            self.patient_user,
            self._create_payload(
                description="چەند ڕۆژێکە ئازاری بەردەوام لە سەرم هەیە",
            ),
        )
        self.assertEqual(kurdish.status_code, 201)

        with CaptureQueriesContext(connection) as captured:
            response = self._post_as(self.patient_user)
            self.assertEqual(response.status_code, 201)
        self.assertLessEqual(len(captured), 14)

    def test_create_permissions(self):
        doctor_response = self._post_as(self.doctor.user)
        self.assertEqual(doctor_response.status_code, 403)
        coordinator = User.objects.create_user(
            email="coordinator@example.test",
            role=UserRole.COORDINATOR,
        )
        self.assertEqual(self._post_as(coordinator).status_code, 403)
        administrator = User.objects.create_user(
            email="administrator@example.test",
            role=UserRole.ADMINISTRATOR,
        )
        self.assertEqual(self._post_as(administrator).status_code, 403)
        self.client.force_authenticate(user=None)
        anonymous = self.client.post(
            self.create_url,
            self._create_payload(),
            format="json",
        )
        self.assertEqual(anonymous.status_code, 401)
