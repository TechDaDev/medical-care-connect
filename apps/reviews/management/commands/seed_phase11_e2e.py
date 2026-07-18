"""Seed Phase 11 E2E test data.

Usage:
    python manage.py seed_phase11_e2e --run-id <id> [--execute]
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import secrets

from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.doctors.models import DoctorProfile
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty
from apps.reviews.models import ConsultationReview, ReviewStatus, DoctorReviewResponse


class Command(BaseCommand):
    help = "Seed Phase 11 E2E test data"

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True, help="Unique run identifier")
        parser.add_argument("--execute", action="store_true", help="Actually create records")

    def handle(self, *args, **options):
        run_id = options["run_id"]
        execute = options["execute"]

        if not run_id.isalnum() or len(run_id) > 32:
            raise CommandError("run-id must be alphanumeric, max 32 chars")

        if not execute:
            self.stdout.write(self.style.WARNING("DRY RUN - add --execute to commit"))
            self.stdout.write(f"Would create Phase 11 E2E data for run: {run_id}")
            return

        with transaction.atomic():
            spec, _ = Specialty.objects.get_or_create(
                slug=f"e2e-{run_id}", defaults={"name": f"E2E {run_id[:6]}", "is_active": True}
            )

            coord, _ = User.objects.get_or_create(
                email=f"coord-{run_id}@e2e.mcc.dev",
                defaults={
                    "role": UserRole.COORDINATOR, "is_staff": True, "is_active": True,
                    "first_name": f"Coord{run_id[:6]}", "last_name": "E2E",
                },
            )
            coord.set_password(secrets.token_urlsafe(16))
            coord.save()

            doc_a_user = User.objects.create_user(
                email=f"doctor-a-{run_id}@e2e.mcc.dev",
                password=secrets.token_urlsafe(16),
                role=UserRole.DOCTOR, first_name=f"DocA{run_id[:6]}", last_name="E2E",
            )
            doc_a_prof, _ = DoctorProfile.objects.get_or_create(
                user=doc_a_user,
                defaults={
                    "is_approved": True, "is_accepting_consultations": True,
                    "specialty": spec, "license_number": f"LIC-A-{run_id}",
                }
            )

            doc_b_user = User.objects.create_user(
                email=f"doctor-b-{run_id}@e2e.mcc.dev",
                password=secrets.token_urlsafe(16),
                role=UserRole.DOCTOR, first_name=f"DocB{run_id[:6]}", last_name="E2E",
            )
            doc_b_prof, _ = DoctorProfile.objects.get_or_create(
                user=doc_b_user,
                defaults={
                    "is_approved": True, "is_accepting_consultations": True,
                    "specialty": spec, "license_number": f"LIC-B-{run_id}",
                }
            )

            pat_a_user = User.objects.create_user(
                email=f"patient-a-{run_id}@e2e.mcc.dev",
                password=secrets.token_urlsafe(16),
                role=UserRole.PATIENT, first_name=f"PatA{run_id[:6]}", last_name="E2E",
            )
            pat_a_prof, _ = PatientProfile.objects.get_or_create(user=pat_a_user)

            pat_b_user = User.objects.create_user(
                email=f"patient-b-{run_id}@e2e.mcc.dev",
                password=secrets.token_urlsafe(16),
                role=UserRole.PATIENT, first_name=f"PatB{run_id[:6]}", last_name="E2E",
            )
            pat_b_prof, _ = PatientProfile.objects.get_or_create(user=pat_b_user)

            completed_cons = Consultation.objects.create(
                patient=pat_a_prof,
                doctor=doc_a_prof,
                specialty=spec,
                status=ConsultationStatus.COMPLETED,
                description="E2E test consultation",
            )

            active_cons = Consultation.objects.create(
                patient=pat_a_prof,
                doctor=doc_a_prof,
                specialty=spec,
                status=ConsultationStatus.ACCEPTED,
                description="E2E active consultation",
            )

            review = ConsultationReview.objects.create(
                consultation=completed_cons,
                reviewer=pat_a_prof,
                rating=5,
                title="E2E test review",
                body="This is an automated E2E test review.",
                is_anonymous=True,
                status=ReviewStatus.PUBLISHED,
            )

            DoctorReviewResponse.objects.create(
                review=review,
                doctor=doc_a_prof,
                body="Thank you for your feedback.",
            )

            self.stdout.write(self.style.SUCCESS(f"Seeded Phase 11 E2E data (run={run_id})"))
            self.stdout.write(f"  Coordinator: coord-{run_id}@e2e.mcc.dev")
            self.stdout.write(f"  Doctor A: doctor-a-{run_id}@e2e.mcc.dev")
            self.stdout.write(f"  Doctor B: doctor-b-{run_id}@e2e.mcc.dev")
            self.stdout.write(f"  Patient A: patient-a-{run_id}@e2e.mcc.dev")
            self.stdout.write(f"  Patient B: patient-b-{run_id}@e2e.mcc.dev")
            self.stdout.write(f"  Completed consultation: {completed_cons.id}")
            self.stdout.write(f"  Active consultation: {active_cons.id}")
            self.stdout.write(f"  Published review: {review.id}")
            self.stdout.write(self.style.WARNING("Credentials not printed. Use railway shell or env vars."))
