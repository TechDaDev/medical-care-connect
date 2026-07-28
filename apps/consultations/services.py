from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.audit_service import create_audit_event
from apps.core.models import AuditEventCategory
from apps.doctors.models import DoctorProfile
from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification
from apps.patients.models import PatientProfile


class ConsultationCreationError(Exception):
    def __init__(self, code: str, *, field: str = "doctor"):
        super().__init__(code)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class ConsultationCreationResult:
    consultation: Consultation
    created: bool


def _validate_doctor(
    doctor: DoctorProfile,
    patient: PatientProfile,
    *,
    specialty_id: UUID | None,
    expected_updated_at: datetime | None,
) -> None:
    if doctor.user_id == patient.user_id:
        raise ConsultationCreationError("doctor_profile_unavailable")
    if not doctor.user.is_active:
        raise ConsultationCreationError("doctor_profile_unavailable")
    if (
        not doctor.is_approved
        or doctor.approval_status != DoctorProfile.ApprovalStatus.APPROVED
    ):
        raise ConsultationCreationError("doctor_profile_unavailable")
    if not doctor.is_accepting_consultations:
        raise ConsultationCreationError("doctor_not_accepting")
    if doctor.specialty is None or not doctor.specialty.is_active:
        raise ConsultationCreationError(
            "specialty_inactive",
            field="specialty",
        )
    if specialty_id is not None and specialty_id != doctor.specialty_id:
        raise ConsultationCreationError(
            "specialty_mismatch",
            field="specialty",
        )
    if (
        expected_updated_at is not None
        and doctor.updated_at != expected_updated_at
    ):
        raise ConsultationCreationError("doctor_state_changed")


@transaction.atomic
def create_patient_consultation(
    *,
    patient: PatientProfile,
    doctor_id: UUID,
    description: str,
    client_request_id: UUID,
    priority: str,
    specialty_id: UUID | None = None,
    expected_doctor_updated_at: datetime | None = None,
    request_id: str = "",
) -> ConsultationCreationResult:
    """Create once per patient request ID with atomic safe side effects."""
    locked_patient = PatientProfile.objects.select_for_update().get(pk=patient.pk)
    existing = (
        Consultation.objects.select_related(
            "doctor__user",
            "specialty",
        )
        .filter(
            patient=locked_patient,
            client_request_id=client_request_id,
        )
        .first()
    )
    if existing is not None:
        same_request = (
            existing.doctor_id == doctor_id
            and existing.description == description
            and (
                specialty_id is None
                or existing.specialty_id == specialty_id
            )
        )
        if not same_request:
            raise ConsultationCreationError(
                "duplicate_request",
                field="client_request_id",
            )
        return ConsultationCreationResult(existing, created=False)

    doctor = (
        DoctorProfile.objects.select_for_update()
        .filter(pk=doctor_id)
        .first()
    )
    if doctor is None:
        raise ConsultationCreationError("doctor_profile_unavailable")

    _validate_doctor(
        doctor,
        locked_patient,
        specialty_id=specialty_id,
        expected_updated_at=expected_doctor_updated_at,
    )

    submitted_at = timezone.now()
    consultation = Consultation.objects.create(
        patient=locked_patient,
        doctor=doctor,
        specialty=doctor.specialty,
        priority=priority,
        description=description,
        status=ConsultationStatus.SUBMITTED,
        submitted_at=submitted_at,
        client_request_id=client_request_id,
    )
    create_audit_event(
        "patient_consultation_created",
        AuditEventCategory.CONSULTATION,
        actor_id=str(locked_patient.user_id),
        actor_role="patient",
        target_type="consultation",
        target_id=str(consultation.id),
        request_id=request_id,
        summary="Patient consultation created.",
        metadata={
            "consultation_id": str(consultation.id),
            "doctor_id": str(doctor.id),
            "specialty_id": str(doctor.specialty_id),
            "initial_status": ConsultationStatus.SUBMITTED,
            "client_request_id": str(client_request_id),
            "result": "created",
        },
        source="consultation_create",
    )
    create_notification(
        recipient=doctor.user,
        notification_type=NotificationType.NEW_CONSULTATION,
        title="New consultation received",
        body="Open the consultation to review the request.",
        consultation=consultation,
    )
    consultation.refresh_from_db()
    return ConsultationCreationResult(consultation, created=True)
