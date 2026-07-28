"""Local-only synthetic Phase F acceptance fixtures."""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from io import BytesIO

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.ai_intake.models import (
    AIIntakeMessage,
    AIIntakeSession,
    EmergencyLevel,
    IntakeSessionStatus,
)
from apps.attachments.choices import AttachmentStatus, ScanStatus
from apps.attachments.models import ConsultationAttachment
from apps.attachments.services.factory import clear_backend_cache, get_storage_backend
from apps.consultations.models import Consultation, ConsultationStatus, Priority
from apps.core.models import (
    AuditEvent,
    AuditEventCategory,
    AuditEventResult,
    AuditEventSeverity,
)
from apps.doctors.models import DoctorProfile, LicenseDocument
from apps.messaging.models import ConsultationMessage, MessageReadReceipt, MessageType
from apps.medical_records.models import MedicalRecordDraft, RecordStatus
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.privacy.models import (
    AccountDeletionRequest,
    DataExportRequest,
    DeletionStatus,
    ExportStatus,
)
from apps.reviews.models import (
    ConsultationReview,
    DoctorReviewResponse,
    ReviewReport,
    ReviewStatus,
)
from apps.specialties.models import Specialty
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")


def validate_local_e2e(run_id: str) -> str:
    run_id = run_id.strip().lower()
    if not RUN_ID_RE.fullmatch(run_id):
        raise CommandError("run-id must match [a-z0-9][a-z0-9-]{2,31}")
    if not settings.DEBUG:
        raise CommandError("Refusing synthetic fixture operation when DEBUG is false.")
    database_host = str(settings.DATABASES["default"].get("HOST", "")).lower()
    allowed_hosts = {"", "localhost", "127.0.0.1", "db"}
    if database_host not in allowed_hosts:
        raise CommandError("Refusing synthetic fixture operation on non-local database host.")
    if getattr(settings, "ATTACHMENT_STORAGE_BACKEND", "local") != "local":
        raise CommandError("E2E fixtures require local attachment storage.")
    return run_id


def marker(run_id: str) -> str:
    return f"e2e-{run_id}"


def fixture_email(run_id: str, role: str) -> str:
    return f"e2e+{run_id}+{role}@example.invalid"


def _user(run_id: str, role_name: str, role: str, password: str) -> User:
    user = User.objects.create_user(
        email=fixture_email(run_id, role_name),
        password=password,
        role=role,
        first_name="Synthetic",
        last_name=f"{role_name.replace('-', ' ').title()} {run_id}",
        is_active=True,
    )
    user.is_staff = role == UserRole.ADMINISTRATOR
    user.save(update_fields=["is_staff"])
    return user


@transaction.atomic
def seed(run_id: str, password: str) -> dict[str, int]:
    run_id = validate_local_e2e(run_id)
    cleanup(run_id, verify=False)
    prefix = marker(run_id)

    specialty = Specialty.objects.create(
        name=f"Synthetic Medicine {run_id}",
        name_en=f"Synthetic Medicine {run_id}",
        name_ar=f"طب اصطناعي {run_id}",
        name_ckb=f"پزیشکی دەستکرد {run_id}",
        slug=prefix,
        description=f"{prefix} fixture",
        display_order=9000,
    )
    Specialty.objects.create(
        name=f"Synthetic Inactive Medicine {run_id}",
        name_en=f"Synthetic Inactive Medicine {run_id}",
        name_ar=f"طب اصطناعي غير نشط {run_id}",
        name_ckb=f"پزیشکی دەستکردی ناچالاک {run_id}",
        slug=f"{prefix}-inactive",
        description=f"{prefix} inactive fixture",
        is_active=False,
        display_order=9001,
    )
    admin = _user(run_id, "admin", UserRole.ADMINISTRATOR, password)
    _user(run_id, "secondary-admin", UserRole.ADMINISTRATOR, password)
    _user(run_id, "coordinator", UserRole.COORDINATOR, password)
    patient_user = _user(run_id, "patient", UserRole.PATIENT, password)
    patient = PatientProfile.objects.create(user=patient_user, preferred_language="en")
    complete_patient_user = _user(
        run_id, "patient-complete", UserRole.PATIENT, password
    )
    PatientProfile.objects.create(
        user=complete_patient_user,
        date_of_birth=date(1990, 1, 1),
        preferred_language="en",
        address=f"{prefix} synthetic address",
        emergency_contact_name=f"{prefix} synthetic contact",
        emergency_contact_phone="+9640000000000",
        notes=f"{prefix} non-clinical fixture",
    )

    doctors: dict[str, DoctorProfile] = {}
    for state in ("pending", "approved", "suspended", "unavailable"):
        doctor_user = _user(run_id, state, UserRole.DOCTOR, password)
        approval_status = (
            DoctorProfile.ApprovalStatus.APPROVED
            if state in {"approved", "unavailable"}
            else state
        )
        doctors[state] = DoctorProfile.objects.create(
            user=doctor_user,
            specialty=specialty,
            professional_title=f"Synthetic {state.title()} Doctor",
            license_number=f"{prefix}-{state}",
            approval_status=approval_status,
            is_approved=state in {"approved", "suspended", "unavailable"},
            is_accepting_consultations=state == "approved",
            biography=f"{prefix} non-clinical fixture",
            qualifications=f"{prefix} synthetic qualification",
            workplace_name="Synthetic Medical Center",
            years_of_experience=12 if state == "approved" else 7,
            consultation_fee="75.00" if state == "approved" else "45.00",
            estimated_response_minutes=45 if state == "approved" else 180,
            languages=["en", "ar", "ckb"],
        )

    consultations = []
    lifecycle_states = tuple(ConsultationStatus.values)
    for index, status in enumerate(lifecycle_states):
        priority = (
            Priority.URGENT
            if status == ConsultationStatus.SUBMITTED
            else Priority.HIGH
            if status == ConsultationStatus.EMERGENCY_ESCALATED
            else Priority.LOW
            if status in {ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED}
            else Priority.MEDIUM
        )
        consultations.append(
            Consultation.objects.create(
                patient=patient,
                doctor=doctors["approved"],
                specialty=specialty,
                status=status,
                priority=priority,
                description=f"{prefix} synthetic consultation {index}",
                submitted_at=timezone.now(),
            )
        )

    submitted_consultation = consultations[
        lifecycle_states.index(ConsultationStatus.SUBMITTED)
    ]
    completed_consultation = consultations[
        lifecycle_states.index(ConsultationStatus.COMPLETED)
    ]
    ConsultationMessage.objects.create(
        consultation=submitted_consultation,
        sender=patient_user,
        message_type=MessageType.TEXT,
        content=f"{prefix} synthetic message",
    )
    incoming_message = ConsultationMessage.objects.create(
        consultation=submitted_consultation,
        sender=doctors["approved"].user,
        message_type=MessageType.TEXT,
        content=f"{prefix} read synthetic doctor message",
    )
    MessageReadReceipt.objects.create(message=incoming_message, user=patient_user)
    unread_message = ConsultationMessage.objects.create(
        consultation=submitted_consultation,
        sender=doctors["approved"].user,
        message_type=MessageType.TEXT,
        content=f"{prefix} synthetic incoming message",
    )
    incomplete_intake = AIIntakeSession.objects.create(
        consultation=consultations[
            lifecycle_states.index(ConsultationStatus.INTAKE_IN_PROGRESS)
        ],
        status=IntakeSessionStatus.IN_PROGRESS,
        current_question=f"{prefix} synthetic question",
        question_count=1,
        started_at=timezone.now(),
    )
    AIIntakeMessage.objects.create(
        session=incomplete_intake,
        role="assistant",
        content=f"{prefix} synthetic intake question",
        sequence_number=1,
    )
    completed_intake = AIIntakeSession.objects.create(
        consultation=consultations[
            lifecycle_states.index(ConsultationStatus.INTAKE_COMPLETED)
        ],
        status=IntakeSessionStatus.CONFIRMED,
        question_count=2,
        started_at=timezone.now() - timedelta(minutes=5),
        completed_at=timezone.now(),
        confirmed_at=timezone.now(),
    )
    AIIntakeMessage.objects.create(
        session=completed_intake,
        role="patient",
        content=f"{prefix} synthetic completed intake response",
        sequence_number=1,
    )
    AIIntakeSession.objects.create(
        consultation=consultations[
            lifecycle_states.index(ConsultationStatus.EMERGENCY_ESCALATED)
        ],
        status=IntakeSessionStatus.EMERGENCY_STOPPED,
        emergency_detected=True,
        emergency_level=EmergencyLevel.EMERGENCY,
        emergency_reasons=[f"{prefix} synthetic emergency rule"],
        started_at=timezone.now(),
        completed_at=timezone.now(),
    )
    ConsultationReview.objects.create(
        consultation=completed_consultation,
        reviewer=patient,
        rating=5,
        title=f"{prefix} synthetic published review",
        body="Synthetic local acceptance review.",
        status=ReviewStatus.PUBLISHED,
    )
    MedicalRecordDraft.objects.create(
        consultation=completed_consultation,
        status=RecordStatus.FINALIZED,
        chief_complaint=f"{prefix} synthetic patient-visible record",
        history_of_present_illness="Synthetic local acceptance history.",
        symptoms=["synthetic symptom"],
        severity=2,
        finalized_at=timezone.now(),
        doctor_notes="Internal synthetic note; never patient-visible.",
    )
    AccountDeletionRequest.objects.create(
        subject_user=patient_user,
        requested_by=patient_user,
        reason=f"{prefix} pending synthetic privacy request",
    )
    second_patient_user = _user(run_id, "patient-reject", UserRole.PATIENT, password)
    PatientProfile.objects.create(user=second_patient_user, preferred_language="en")
    AccountDeletionRequest.objects.create(
        subject_user=second_patient_user,
        requested_by=second_patient_user,
        reason=f"{prefix} reject synthetic privacy request",
    )
    deletion_history_user = _user(
        run_id, "patient-deletion-history", UserRole.PATIENT, password
    )
    PatientProfile.objects.create(user=deletion_history_user, preferred_language="en")
    AccountDeletionRequest.objects.create(
        subject_user=deletion_history_user,
        requested_by=deletion_history_user,
        status=DeletionStatus.REJECTED,
        reason=f"{prefix} rejected synthetic privacy history",
        reviewed_at=timezone.now(),
        reviewed_by=admin,
        rejection_reason=f"{prefix} synthetic rejection",
    )
    Notification.objects.create(
        recipient=admin,
        notification_type=NotificationType.STATUS_CHANGE,
        title=f"{prefix} in-app notification",
        body="Synthetic local acceptance notification.",
    )
    Notification.objects.create(
        recipient=patient_user,
        notification_type=NotificationType.NEW_MESSAGE,
        title=f"{prefix} patient dashboard notification",
        body="Synthetic local patient notification.",
        consultation=submitted_consultation,
        related_message=incoming_message,
    )
    Notification.objects.create(
        recipient=patient_user,
        notification_type=NotificationType.NEW_MESSAGE,
        title=f"{prefix} unread patient notification",
        body="Synthetic unread local patient notification.",
        consultation=submitted_consultation,
        related_message=unread_message,
    )
    AuditEvent.objects.create(
        event_type="e2e_fixture_seeded",
        category=AuditEventCategory.SYSTEM,
        severity=AuditEventSeverity.INFO,
        result=AuditEventResult.SUCCESS,
        actor_id=admin.id,
        actor_role=admin.role,
        target_type="e2e_run",
        target_id=run_id,
        request_id=prefix,
        summary=f"{prefix} synthetic audit event",
        metadata={"e2e_run_id": run_id},
        source="seed_e2e_data",
    )

    clear_backend_cache()
    storage = get_storage_backend()
    attachment_specs = (
        ("pending", AttachmentStatus.PENDING, ScanStatus.PENDING),
        ("clean", AttachmentStatus.AVAILABLE, ScanStatus.CLEAN),
        ("quarantined", AttachmentStatus.QUARANTINED, ScanStatus.FAILED),
        ("rejected", AttachmentStatus.REJECTED, ScanStatus.INFECTED),
        ("retention", AttachmentStatus.DELETED, ScanStatus.CLEAN),
    )
    for name, status, scan_status in attachment_specs:
        content = f"{prefix} synthetic attachment {name}\n".encode()
        storage_key = f"{prefix}/{name}.txt"
        storage.save(BytesIO(content), storage_key)
        is_retention = name == "retention"
        ConsultationAttachment.objects.create(
            consultation=completed_consultation,
            uploaded_by=patient_user,
            storage_provider="local",
            storage_key=storage_key,
            original_filename=f"{prefix}-{name}.txt",
            safe_display_name=f"synthetic-{name}.txt",
            extension=".txt",
            declared_mime_type="text/plain",
            detected_mime_type="text/plain",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            status=status,
            scan_status=scan_status,
            scan_provider="synthetic",
            scan_completed_at=None if name == "pending" else timezone.now(),
            quarantine_reason="Synthetic quarantine fixture" if name == "quarantined" else "",
            rejection_reason="Synthetic unsafe fixture" if name == "rejected" else "",
            is_deleted=is_retention,
            deleted_at=timezone.now() - timedelta(days=120) if is_retention else None,
            deletion_reason="Synthetic retention fixture" if is_retention else "",
        )

    export_specs = (
        ("pending", ExportStatus.PENDING, False),
        ("completed", ExportStatus.COMPLETED, True),
        ("expired", ExportStatus.EXPIRED, True),
    )
    for name, export_status, has_archive in export_specs:
        storage_key = f"{prefix}/exports/{name}.zip" if has_archive else ""
        archive = f"{prefix} synthetic export archive {name}\n".encode()
        if storage_key:
            storage.save(BytesIO(archive), storage_key)
        DataExportRequest.objects.create(
            requested_by=patient_user,
            subject_user=patient_user,
            status=export_status,
            started_at=timezone.now() if has_archive else None,
            completed_at=timezone.now() if has_archive else None,
            expires_at=(
                timezone.now() - timedelta(days=1)
                if export_status == ExportStatus.EXPIRED
                else timezone.now() + timedelta(days=7)
                if has_archive
                else None
            ),
            storage_provider="local" if has_archive else "",
            storage_key=storage_key,
            checksum=hashlib.sha256(archive).hexdigest() if has_archive else "",
            size_bytes=len(archive) if has_archive else None,
        )

    return {
        "users": User.objects.filter(email__startswith=f"e2e+{run_id}+").count(),
        "consultations": len(consultations),
        "attachments": len(attachment_specs),
        "privacy_requests": 3,
        "privacy_exports": len(export_specs),
        "intake_sessions": 3,
    }


@transaction.atomic
def cleanup(run_id: str, *, verify: bool = True) -> dict[str, int]:
    run_id = validate_local_e2e(run_id)
    prefix = marker(run_id)
    users = User.objects.filter(
        Q(email__startswith=f"e2e+{run_id}+")
        | Q(first_name="Synthetic", last_name__endswith=f" {run_id}")
    )
    user_ids = list(users.values_list("id", flat=True))
    consultations = Consultation.objects.filter(
        Q(description__startswith=prefix)
        | Q(patient__user_id__in=user_ids)
    )
    consultation_ids = [
        str(value)
        for value in consultations.values_list("id", flat=True)
    ]
    attachments = ConsultationAttachment.objects.filter(storage_key__startswith=f"{prefix}/")
    license_documents = LicenseDocument.objects.filter(doctor_profile__user_id__in=user_ids)
    keys = set(attachments.values_list("storage_key", flat=True))
    keys.update(license_documents.values_list("storage_key", flat=True))
    keys.update(
        f"{prefix}/{name}.txt"
        for name in ("pending", "clean", "quarantined", "rejected", "retention")
    )
    keys.update(
        DataExportRequest.objects.filter(
            subject_user_id__in=user_ids,
            storage_key__startswith=f"{prefix}/",
        ).values_list("storage_key", flat=True)
    )

    clear_backend_cache()
    storage = get_storage_backend()
    for storage_key in keys:
        storage.delete(storage_key)

    attachments.delete()
    license_documents.delete()
    OutstandingToken.objects.filter(user_id__in=user_ids).delete()
    Session.objects.filter(session_key__startswith=prefix).delete()
    AccountDeletionRequest.objects.filter(reason__startswith=prefix).delete()
    DataExportRequest.objects.filter(subject_user_id__in=user_ids).delete()
    AuditEvent.objects.filter(
        target_type="consultation",
        target_id__in=consultation_ids,
    ).delete()
    consultations.delete()
    Notification.objects.filter(title__startswith=prefix).delete()
    users.delete()
    Specialty.objects.filter(slug__startswith=prefix).delete()
    AuditEvent.objects.filter(request_id=prefix, source="seed_e2e_data").delete()

    remaining = {
        "users": User.objects.filter(
            Q(email__startswith=f"e2e+{run_id}+")
            | Q(first_name="Synthetic", last_name__endswith=f" {run_id}")
        ).count(),
        "patient_profiles": PatientProfile.objects.filter(user_id__in=user_ids).count(),
        "doctor_profiles": DoctorProfile.objects.filter(user_id__in=user_ids).count(),
        "consultations": Consultation.objects.filter(description__startswith=prefix).count(),
        "intake_sessions": AIIntakeSession.objects.filter(
            consultation_id__in=consultation_ids
        ).count(),
        "intake_messages": AIIntakeMessage.objects.filter(
            content__startswith=prefix
        ).count(),
        "attachments": ConsultationAttachment.objects.filter(
            storage_key__startswith=f"{prefix}/"
        ).count(),
        "privacy_requests": AccountDeletionRequest.objects.filter(
            reason__startswith=prefix
        ).count(),
        "notifications": Notification.objects.filter(title__startswith=prefix).count(),
        "messages": ConsultationMessage.objects.filter(content__startswith=prefix).count(),
        "read_receipts": MessageReadReceipt.objects.filter(
            user_id__in=user_ids
        ).count(),
        "medical_records": MedicalRecordDraft.objects.filter(
            chief_complaint__startswith=prefix
        ).count(),
        "reviews": ConsultationReview.objects.filter(
            title__startswith=prefix
        ).count(),
        "review_responses": DoctorReviewResponse.objects.filter(
            review__title__startswith=prefix
        ).count(),
        "review_reports": ReviewReport.objects.filter(
            review__title__startswith=prefix
        ).count(),
        "privacy_exports": DataExportRequest.objects.filter(
            subject_user_id__in=user_ids
        ).count(),
        "tokens": OutstandingToken.objects.filter(user_id__in=user_ids).count(),
        "sessions": Session.objects.filter(session_key__startswith=prefix).count(),
        "license_documents": LicenseDocument.objects.filter(
            doctor_profile__user_id__in=user_ids
        ).count(),
        "specialties": Specialty.objects.filter(slug__startswith=prefix).count(),
        "audit_events": AuditEvent.objects.filter(
            request_id=prefix, source="seed_e2e_data"
        ).count(),
        "storage_objects": sum(1 for key in keys if storage.exists(key)),
        "idempotency_markers": Consultation.objects.filter(
            description__startswith=prefix,
            client_request_id__isnull=False,
        ).count(),
    }
    if verify and any(remaining.values()):
        raise CommandError(f"Synthetic cleanup incomplete: {remaining}")
    return remaining
