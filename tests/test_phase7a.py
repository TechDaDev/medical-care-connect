"""Phase 7A tests: integration hardening, staff APIs, dashboards, seed, errors."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.consultations.models import (
    Consultation,
    ConsultationPriorityChange,
    ConsultationStatus,
    ConsultationTransfer,
)
from apps.doctors.models import DoctorProfile
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


def _create_user(email, role=UserRole.PATIENT, first="Test", last="User"):
    user = User.objects.create_user(
        email=email,
        password="testpass123",
        first_name=first,
        last_name=last,
        role=role,
    )
    if role == UserRole.ADMINISTRATOR or role == UserRole.COORDINATOR:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return user


def _create_patient(user):
    return PatientProfile.objects.get_or_create(
        user=user,
        defaults={"gender": "not_specified", "preferred_language": "en"},
    )[0]


def _create_doctor(user, specialty=None):
    if specialty is None:
        specialty = Specialty.objects.create(
            name="Test Specialty", slug="test-spec"
        )
    return DoctorProfile.objects.get_or_create(
        user=user,
        defaults={
            "specialty": specialty,
            "license_number": f"LIC-{user.id.hex[:8]}",
            "is_approved": True,
            "is_accepting_consultations": True,
        },
    )[0]


def _login(client, email="test@example.com"):
    resp = client.post(
        "/api/auth/login/",
        {"email": email, "password": "testpass123"},
        format="json",
    )
    token = resp.cookies.get("mcc_access")
    token_value = token.value if token else None
    client.cookies.clear()
    return token_value


# ── Test 1: Seed command idempotence ────────────────────────────────────────


class SeedCommandTests(TestCase):
    def test_seed_is_idempotent(self):
        """Running seed twice does not create duplicate records."""
        from django.core.management import call_command

        call_command("seed_development_data", force=True)
        count_before = User.objects.count()

        call_command("seed_development_data", force=True)
        count_after = User.objects.count()

        self.assertEqual(count_before, count_after)


# ── Test 2: Patient dashboard scoped ────────────────────────────────────────


class PatientDashboardTests(TestCase):
    def test_patient_dashboard_scoped(self):
        """Patient dashboard only returns own data."""
        user1 = _create_user("p1@test.com", UserRole.PATIENT)
        _create_patient(user1)
        user2 = _create_user("p2@test.com", UserRole.PATIENT)
        _create_patient(user2)

        doc_user = _create_user("doc@test.com", UserRole.DOCTOR)
        doc = _create_doctor(doc_user)
        spec = Specialty.objects.first()

        Consultation.objects.create(
            patient=user1.patient_profile, doctor=doc,
            specialty=spec, status=ConsultationStatus.SUBMITTED,
        )
        Consultation.objects.create(
            patient=user2.patient_profile, doctor=doc,
            specialty=spec, status=ConsultationStatus.COMPLETED,
        )

        client = APIClient()
        token = _login(client, "p1@test.com")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.get("/api/patients/me/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["consultations"]["total"], 1)
        self.assertEqual(resp.data["consultations"]["active"], 1)


# ── Test 3: Doctor dashboard scoped ─────────────────────────────────────────


class DoctorDashboardTests(TestCase):
    def test_doctor_dashboard_scoped(self):
        """Doctor dashboard only returns assigned consultations."""
        doc_user = _create_user("doc@test.com", UserRole.DOCTOR)
        doc = _create_doctor(doc_user)

        pat1 = _create_patient(_create_user("p1@test.com"))
        pat2 = _create_patient(_create_user("p2@test.com"))
        spec = Specialty.objects.first()

        Consultation.objects.create(
            patient=pat1, doctor=doc, specialty=spec,
            status=ConsultationStatus.SUBMITTED,
        )
        Consultation.objects.create(
            patient=pat2, doctor=doc, specialty=spec,
            status=ConsultationStatus.COMPLETED,
        )

        client = APIClient()
        token = _login(client, "doc@test.com")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.get("/api/doctors/me/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["consultations"]["total_active"], 1)


# ── Test 4: Staff dashboard rejects non-staff ───────────────────────────────


class StaffAuthTests(TestCase):
    def test_staff_dashboard_rejects_patient(self):
        """Non-staff users cannot access staff dashboard."""
        user = _create_user("pat@test.com")
        _create_patient(user)
        client = APIClient()
        token = _login(client, "pat@test.com")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.get("/api/staff/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ── Test 5: Transfer consultation ───────────────────────────────────────────


class TransferTests(TestCase):
    def test_coordinator_can_transfer(self):
        """Coordinator can transfer a consultation."""
        coord = _create_user("coord@test.com", UserRole.COORDINATOR)
        spec = Specialty.objects.create(name="Cardiology", slug="cardio")
        old_doc = _create_doctor(
            _create_user("old@test.com", UserRole.DOCTOR), spec
        )
        new_doc = _create_doctor(
            _create_user("new@test.com", UserRole.DOCTOR), spec
        )

        pat = _create_patient(_create_user("pat@test.com"))
        consultation = Consultation.objects.create(
            patient=pat, doctor=old_doc, specialty=spec,
            status=ConsultationStatus.SUBMITTED,
        )

        client = APIClient()
        token = _login(client, "coord@test.com")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.post(
            f"/api/staff/consultations/{consultation.id}/transfer/",
            {"doctor_id": str(new_doc.id), "reason": "Specialist required"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, ConsultationStatus.TRANSFERRED)
        self.assertEqual(consultation.doctor_id, new_doc.id)
        self.assertTrue(
            ConsultationTransfer.objects.filter(consultation=consultation).exists()
        )


# ── Test 6: Transfer rejects inactive doctor ────────────────────────────────


class TransferValidationTests(TestCase):
    def test_transfer_rejects_unapproved_doctor(self):
        coord = _create_user("coord@test.com", UserRole.COORDINATOR)
        spec = Specialty.objects.create(name="Cardio", slug="cardio")
        old_doc = _create_doctor(
            _create_user("old@test.com", UserRole.DOCTOR), spec
        )
        new_doc = _create_doctor(
            _create_user("new@test.com", UserRole.DOCTOR), spec
        )
        new_doc.is_approved = False
        new_doc.save(update_fields=["is_approved"])

        pat = _create_patient(_create_user("pat@test.com"))
        consultation = Consultation.objects.create(
            patient=pat, doctor=old_doc, specialty=spec,
            status=ConsultationStatus.SUBMITTED,
        )

        client = APIClient()
        token = _login(client, "coord@test.com")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.post(
            f"/api/staff/consultations/{consultation.id}/transfer/",
            {"doctor_id": str(new_doc.id), "reason": "Need specialist"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not approved", resp.data["detail"])


# ── Test 7: Priority update rejects patient ─────────────────────────────────


class PriorityUpdateTests(TestCase):
    def test_patient_cannot_set_priority(self):
        pat = _create_user("pat@test.com", UserRole.PATIENT)
        _create_patient(pat)
        doc = _create_doctor(_create_user("doc@test.com", UserRole.DOCTOR))
        spec = Specialty.objects.first()
        consultation = Consultation.objects.create(
            patient=pat.patient_profile, doctor=doc, specialty=spec,
            status=ConsultationStatus.SUBMITTED,
        )

        client = APIClient()
        token = _login(client, "pat@test.com")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.patch(
            f"/api/staff/consultations/{consultation.id}/priority/",
            {"priority": "urgent"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ── Test 8: Consultation detail action flags differ by role ─────────────────


class ActionFlagsTests(TestCase):
    def test_action_flags_differ_by_role(self):
        spec = Specialty.objects.create(name="General", slug="general")
        doc = _create_doctor(
            _create_user("doc@test.com", UserRole.DOCTOR), spec
        )
        pat = _create_patient(_create_user("pat@test.com"))

        consultation = Consultation.objects.create(
            patient=pat, doctor=doc, specialty=spec,
            status=ConsultationStatus.SUBMITTED,
        )

        # Patient view
        client = APIClient()
        token = _login(client, "pat@test.com")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.get(f"/api/consultations/{consultation.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("actions", resp.data)
        self.assertFalse(resp.data["actions"]["can_accept"])
        self.assertTrue(resp.data["actions"]["can_cancel"])

        # Doctor view
        client2 = APIClient()
        token2 = _login(client2, "doc@test.com")
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")
        resp2 = client2.get(f"/api/consultations/{consultation.id}/")
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.data["actions"]["can_accept"])
        self.assertTrue(resp2.data["actions"]["can_cancel"])
        self.assertTrue(resp2.data["actions"]["can_add_internal_note"])


# ── Test 9: Readiness endpoint ──────────────────────────────────────────────


class ReadinessTests(TestCase):
    def test_readiness_reports_database_status(self):
        """Readiness endpoint returns database status without secrets."""
        client = APIClient()
        resp = client.get("/api/readiness/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("database", resp.data)
        self.assertIn("ai_intake", resp.data)
        self.assertIn("status", resp.data)
        # Should not leak secrets
        content = str(resp.data)
        self.assertNotIn("key", content.lower())
        self.assertNotIn("password", content.lower())
        self.assertNotIn("secret", content.lower())


# ── Test 10: API error handler ──────────────────────────────────────────────


class ErrorHandlerTests(TestCase):
    def test_validation_error_format(self):
        """Validation errors return normalized format."""
        client = APIClient()
        resp = client.post(
            "/api/auth/register/patient/",
            {"email": "new@test.com", "password": "short"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", resp.data)
        self.assertIn("code", resp.data)
        self.assertEqual(resp.data["code"], "validation_error")

    def test_not_found_format(self):
        """404 errors return normalized format."""
        client = APIClient()
        resp = client.get("/api/doctors/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("code", resp.data)
        self.assertIn("detail", resp.data)
