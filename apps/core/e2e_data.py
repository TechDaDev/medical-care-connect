"""Local-only synthetic Phase F acceptance fixtures."""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
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
from apps.messaging.models import ConsultationMessage, MessageType
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.privacy.models import AccountDeletionRequest
from apps.reviews.models import ConsultationReview, ReviewStatus
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
    admin = _user(run_id, "admin", UserRole.ADMINISTRATOR, password)
    _user(run_id, "secondary-admin", UserRole.ADMINISTRATOR, password)
    _user(run_id, "coordinator", UserRole.COORDINATOR, password)
    patient_user = _user(run_id, "patient", UserRole.PATIENT, password)
    patient = PatientProfile.objects.create(user=patient_user, preferred_language="en")

    doctors: dict[str, DoctorProfile] = {}
    for state in ("pending", "approved", "suspended"):
        doctor_user = _user(run_id, state, UserRole.DOCTOR, password)
        doctors[state] = DoctorProfile.objects.create(
            user=doctor_user,
            specialty=specialty,
            professional_title=f"Synthetic {state.title()} Doctor",
            license_number=f"{prefix}-{state}",
            approval_status=state,
            is_approved=state in {"approved", "suspended"},
            is_accepting_consultations=state == "approved",
            biography=f"{prefix} non-clinical fixture",
            languages=["en", "ar", "ckb"],
        )

    consultations = []
    for index, (status, priority) in enumerate(
        (
            (ConsultationStatus.SUBMITTED, Priority.URGENT),
            (ConsultationStatus.ACCEPTED, Priority.MEDIUM),
            (ConsultationStatus.DOCTOR_REVIEW, Priority.HIGH),
            (ConsultationStatus.COMPLETED, Priority.LOW),
        )
    ):
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

    ConsultationMessage.objects.create(
        consultation=consultations[0],
        sender=patient_user,
        message_type=MessageType.TEXT,
        content=f"{prefix} synthetic message",
    )
    incoming_message = ConsultationMessage.objects.create(
        consultation=consultations[0],
        sender=doctors["approved"].user,
        message_type=MessageType.TEXT,
        content=f"{prefix} synthetic incoming message",
    )
    ConsultationReview.objects.create(
        consultation=consultations[-1],
        reviewer=patient,
        rating=5,
        title=f"{prefix} synthetic published review",
        body="Synthetic local acceptance review.",
        status=ReviewStatus.PUBLISHED,
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
        consultation=consultations[0],
        related_message=incoming_message,
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
            consultation=consultations[-1],
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
            scan_completed_at=timezone.now(),
            quarantine_reason="Synthetic quarantine fixture" if name == "quarantined" else "",
            rejection_reason="Synthetic unsafe fixture" if name == "rejected" else "",
            is_deleted=is_retention,
            deleted_at=timezone.now() - timedelta(days=120) if is_retention else None,
            deletion_reason="Synthetic retention fixture" if is_retention else "",
        )

    return {
        "users": User.objects.filter(email__startswith=f"e2e+{run_id}+").count(),
        "consultations": len(consultations),
        "attachments": len(attachment_specs),
        "privacy_requests": 2,
    }


@transaction.atomic
def cleanup(run_id: str, *, verify: bool = True) -> dict[str, int]:
    run_id = validate_local_e2e(run_id)
    prefix = marker(run_id)
    users = User.objects.filter(email__startswith=f"e2e+{run_id}+")
    user_ids = list(users.values_list("id", flat=True))
    attachments = ConsultationAttachment.objects.filter(storage_key__startswith=f"{prefix}/")
    license_documents = LicenseDocument.objects.filter(doctor_profile__user_id__in=user_ids)
    keys = set(attachments.values_list("storage_key", flat=True))
    keys.update(license_documents.values_list("storage_key", flat=True))
    keys.update(
        f"{prefix}/{name}.txt"
        for name in ("clean", "quarantined", "rejected", "retention")
    )

    clear_backend_cache()
    storage = get_storage_backend()
    for storage_key in keys:
        storage.delete(storage_key)

    attachments.delete()
    license_documents.delete()
    OutstandingToken.objects.filter(user_id__in=user_ids).delete()
    AccountDeletionRequest.objects.filter(reason__startswith=prefix).delete()
    Consultation.objects.filter(description__startswith=prefix).delete()
    Notification.objects.filter(title__startswith=prefix).delete()
    users.delete()
    Specialty.objects.filter(slug=prefix).delete()
    AuditEvent.objects.filter(request_id=prefix, source="seed_e2e_data").delete()

    remaining = {
        "users": User.objects.filter(email__startswith=f"e2e+{run_id}+").count(),
        "consultations": Consultation.objects.filter(description__startswith=prefix).count(),
        "attachments": ConsultationAttachment.objects.filter(
            storage_key__startswith=f"{prefix}/"
        ).count(),
        "privacy_requests": AccountDeletionRequest.objects.filter(
            reason__startswith=prefix
        ).count(),
        "notifications": Notification.objects.filter(title__startswith=prefix).count(),
        "messages": ConsultationMessage.objects.filter(content__startswith=prefix).count(),
        "tokens": OutstandingToken.objects.filter(user_id__in=user_ids).count(),
        "license_documents": LicenseDocument.objects.filter(
            doctor_profile__user_id__in=user_ids
        ).count(),
        "specialties": Specialty.objects.filter(slug=prefix).count(),
        "audit_events": AuditEvent.objects.filter(
            request_id=prefix, source="seed_e2e_data"
        ).count(),
        "storage_objects": sum(1 for key in keys if storage.exists(key)),
    }
    if verify and any(remaining.values()):
        raise CommandError(f"Synthetic cleanup incomplete: {remaining}")
    return remaining
