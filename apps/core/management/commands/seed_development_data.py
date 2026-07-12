"""Development seed data command.

Usage:
    python manage.py seed_development_data
    python manage.py seed_development_data --reset
    python manage.py seed_development_data --force
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.doctors.models import DoctorProfile
from apps.messaging.models import ConsultationMessage, MessageType
from apps.messaging.services import create_consultation_message
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty

_SEED_EMAILS = {
    "admin": "admin@mcc.dev",
    "coordinator": "coordinator@mcc.dev",
    "doctor_ali": "dr.ali@mcc.dev",
    "doctor_sarah": "dr.sarah@mcc.dev",
    "doctor_ahmed": "dr.ahmed@mcc.dev",
    "doctor_emily": "dr.emily@mcc.dev",
    "patient_john": "john.doe@mcc.dev",
    "patient_jane": "jane.smith@mcc.dev",
}

SEED_PASSWORD = "Development123!"


def _get_or_create_specialties():
    specialties_data = [
        ("Cardiology", "cardiology", "Heart and cardiovascular system."),
        ("Dermatology", "dermatology", "Skin, hair, and nail conditions."),
        ("Orthopedics", "orthopedics", "Musculoskeletal system."),
        ("Pediatrics", "pediatrics", "Medical care for children."),
        ("Neurology", "neurology", "Nervous system disorders."),
    ]
    specialties = []
    for name, slug, desc in specialties_data:
        s, _ = Specialty.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "description": desc, "is_active": True},
        )
        specialties.append(s)
    return specialties


def _create_user(email, first_name, last_name, role):
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "role": role,
            "is_active": True,
        },
    )
    if created:
        user.set_password(SEED_PASSWORD)
        user.save()
    return user, created


def _create_patient_profile(user):
    profile, created = PatientProfile.objects.get_or_create(
        user=user,
        defaults={
            "preferred_language": "en",
            "gender": "not_specified",
        },
    )
    return profile


def _create_doctor_profile(user, specialty, title, bio, years, fee, langs):
    profile, created = DoctorProfile.objects.get_or_create(
        user=user,
        defaults={
            "specialty": specialty,
            "professional_title": title,
            "license_number": f"LIC-{user.first_name.upper()}-{user.id.hex[:6]}",
            "qualifications": title,
            "biography": bio,
            "years_of_experience": years,
            "consultation_fee": fee,
            "languages": langs,
            "is_approved": True,
            "is_accepting_consultations": True,
            "estimated_response_minutes": 30,
        },
    )
    return profile


class Command(BaseCommand):
    help = "Seed development data for local testing."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Remove seed data")
        parser.add_argument("--force", action="store_true", help="Run with DEBUG=False")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options.get("force"):
            raise CommandError(
                "Refusing to run in production. Use --force to override."
            )

        if options.get("reset"):
            self._reset()
            self.stdout.write(self.style.SUCCESS("Seed data removed."))
            return

        self._seed()
        self.stdout.write(self.style.SUCCESS("Development data seeded."))
        self._print_credentials()

    def _reset(self):
        emails = list(_SEED_EMAILS.values())
        ConsultationMessage.objects.filter(
            sender__email__in=emails
        ).delete()
        Notification.objects.filter(
            recipient__email__in=emails
        ).delete()
        PatientProfile.objects.filter(user__email__in=emails).delete()
        DoctorProfile.objects.filter(user__email__in=emails).delete()
        User.objects.filter(email__in=emails).delete()

    @transaction.atomic
    def _seed(self):
        specialties = _get_or_create_specialties()

        # Admin
        admin_user, _ = _create_user(
            _SEED_EMAILS["admin"], "Admin", "User", UserRole.ADMINISTRATOR
        )
        admin_user.is_staff = True
        admin_user.save(update_fields=["is_staff"])

        # Coordinator
        coord_user, _ = _create_user(
            _SEED_EMAILS["coordinator"], "Coordinator", "User", UserRole.COORDINATOR
        )

        # Doctors
        dr_ali, _ = _create_user(
            _SEED_EMAILS["doctor_ali"], "Ali", "Hassan", UserRole.DOCTOR
        )
        ali_profile = _create_doctor_profile(
            dr_ali, specialties[0], "Consultant Cardiologist",
            "Experienced cardiologist with 15+ years in interventional cardiology.",
            15, 150.00, ["English", "Arabic"],
        )

        dr_sarah, _ = _create_user(
            _SEED_EMAILS["doctor_sarah"], "Sarah", "Ahmed", UserRole.DOCTOR
        )
        sarah_profile = _create_doctor_profile(
            dr_sarah, specialties[1], "Senior Dermatologist",
            "Specialist in medical and cosmetic dermatology.",
            10, 120.00, ["English"],
        )

        dr_ahmed, _ = _create_user(
            _SEED_EMAILS["doctor_ahmed"], "Ahmed", "Jabbar", UserRole.DOCTOR
        )
        ahmed_profile = _create_doctor_profile(
            dr_ahmed, specialties[2], "Orthopedic Surgeon",
            "Specializing in sports injuries and joint replacement.",
            12, 200.00, ["English", "Arabic"],
        )

        dr_emily, _ = _create_user(
            _SEED_EMAILS["doctor_emily"], "Emily", "Chen", UserRole.DOCTOR
        )
        emily_profile = _create_doctor_profile(
            dr_emily, specialties[3], "Pediatrician",
            "Passionate about children's health and development.",
            8, 100.00, ["English"],
        )

        # Patients
        john_user, _ = _create_user(
            _SEED_EMAILS["patient_john"], "John", "Doe", UserRole.PATIENT
        )
        john_profile = _create_patient_profile(john_user)

        jane_user, _ = _create_user(
            _SEED_EMAILS["patient_jane"], "Jane", "Smith", UserRole.PATIENT
        )
        jane_profile = _create_patient_profile(jane_user)

        # Consultations
        now = timezone.now()

        c1, _ = Consultation.objects.get_or_create(
            patient=john_profile, doctor=sarah_profile,
            status=ConsultationStatus.SUBMITTED,
            defaults={
                "specialty": sarah_profile.specialty,
                "description": "Persistent skin rash on arms for two weeks.",
                "submitted_at": now - timezone.timedelta(hours=2),
                "priority": "medium",
            },
        )

        c2, _ = Consultation.objects.get_or_create(
            patient=jane_profile, doctor=ali_profile,
            status=ConsultationStatus.ACCEPTED,
            defaults={
                "specialty": ali_profile.specialty,
                "description": "Chest discomfort when exercising.",
                "submitted_at": now - timezone.timedelta(hours=5),
                "accepted_at": now - timezone.timedelta(hours=3),
                "priority": "high",
            },
        )

        c3, _ = Consultation.objects.get_or_create(
            patient=john_profile, doctor=ahmed_profile,
            status=ConsultationStatus.DOCTOR_REVIEW,
            defaults={
                "specialty": ahmed_profile.specialty,
                "description": "Knee pain after running. Early arthritis?",
                "submitted_at": now - timezone.timedelta(days=1),
                "accepted_at": now - timezone.timedelta(hours=20),
                "priority": "medium",
            },
        )

        c4, _ = Consultation.objects.get_or_create(
            patient=jane_profile, doctor=emily_profile,
            status=ConsultationStatus.COMPLETED,
            defaults={
                "specialty": emily_profile.specialty,
                "description": "Follow-up on child vaccination.",
                "submitted_at": now - timezone.timedelta(days=3),
                "accepted_at": now - timezone.timedelta(days=2, hours=12),
                "priority": "low",
            },
        )

        c5, _ = Consultation.objects.get_or_create(
            patient=john_profile, doctor=sarah_profile,
            status=ConsultationStatus.CANCELLED,
            defaults={
                "specialty": sarah_profile.specialty,
                "description": "Acne treatment consultation.",
                "submitted_at": now - timezone.timedelta(days=7),
                "cancelled_at": now - timezone.timedelta(days=5),
                "cancellation_reason": "Patient cancelled due to scheduling conflict.",
                "priority": "low",
            },
        )

        # Messages for c2
        msg1, _ = ConsultationMessage.objects.get_or_create(
            consultation=c2, sender=jane_user,
            content="I have been feeling chest tightness when I climb stairs.",
            defaults={"sent_at": now - timezone.timedelta(hours=4)},
        )
        msg2, _ = ConsultationMessage.objects.get_or_create(
            consultation=c2, sender=dr_ali,
            content="How long has this been happening? Any dizziness?",
            defaults={"sent_at": now - timezone.timedelta(hours=3, minutes=30)},
        )

        # Messages for c3
        ConsultationMessage.objects.get_or_create(
            consultation=c3, sender=john_user,
            content="The pain started two weeks ago after a 10K run.",
            defaults={"sent_at": now - timezone.timedelta(hours=22)},
        )

        # Unread notifications
        Notification.objects.get_or_create(
            recipient=john_user,
            notification_type=NotificationType.NEW_MESSAGE,
            title="New message from Dr. Ahmed",
            body="Dr. Ahmed has reviewed your case. Check the consultation.",
            consultation=c3,
            defaults={"is_read": False},
        )

        Notification.objects.get_or_create(
            recipient=dr_ahmed,
            notification_type=NotificationType.CONSULTATION_ACCEPTED,
            title="Consultation accepted",
            body="You have accepted the consultation.",
            consultation=c3,
            defaults={"is_read": True},
        )

        # Internal note on c3
        from apps.messaging.models import DoctorInternalNote
        DoctorInternalNote.objects.get_or_create(
            consultation=c3, author=dr_ahmed,
            defaults={
                "content": "Patient reports knee pain post-running. "
                "Will review further if needed.",
            },
        )

        # One medical record draft (confirmed) for c4
        from apps.medical_records.models import MedicalRecordDraft
        MedicalRecordDraft.objects.get_or_create(
            consultation=c4,
            defaults={
                "status": "finalized",
                "chief_complaint": "Child vaccination follow-up.",
                "history_of_present_illness": "Routine checkup post-vaccination.",
                "symptoms": [],
                "severity": 1,
                "duration": "N/A",
                "past_medical_history": "No significant history.",
                "medications": [],
                "allergies": [],
            },
        )

    def _print_credentials(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  Development Accounts"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("")
        self.stdout.write(f"  Password for all accounts: {SEED_PASSWORD}")
        self.stdout.write("")
        for label, email in _SEED_EMAILS.items():
            self.stdout.write(f"  {label:20s} → {email}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
