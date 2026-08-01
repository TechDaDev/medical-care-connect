"""Authoritative Doctor Phase C medical-record commands and policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.audit_service import create_audit_event
from apps.core.models import AuditEventCategory
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import (
    MedicalRecordAction,
    MedicalRecordDraft,
    RecordStatus,
)
from apps.notifications.models import Notification, NotificationType


DOCTOR_AUTHORED_FIELDS = (
    "clinical_summary",
    "assessment",
    "working_diagnosis",
    "differential_considerations",
    "recommendations",
    "treatment_plan",
    "follow_up_plan",
    "physical_visit_reason",
    "warning_signs",
    "patient_instructions",
    "doctor_notes",
)

CREATE_ALLOWED_STATUSES = {
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.INTAKE_IN_PROGRESS,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_PATIENT_RESPONSE,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
    ConsultationStatus.UNDER_REVIEW,
    ConsultationStatus.FOLLOW_UP_REQUIRED,
    ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
    ConsultationStatus.TRANSFERRED,
}


class MedicalRecordWorkflowError(Exception):
    def __init__(self, code: str, *, http_status: int = 409, details=None):
        self.code = code
        self.http_status = http_status
        self.details = details
        super().__init__(code)


@dataclass(frozen=True)
class RecordValidation:
    can_finalize: bool
    missing_fields: list[str]
    warnings: list[str]
    blocking_errors: list[str]


def validate_record_for_finalization(record: MedicalRecordDraft) -> RecordValidation:
    missing = []
    if not (record.clinical_summary.strip() or record.assessment.strip()):
        missing.append("clinical_summary_or_assessment")
    if not record.patient_instructions.strip():
        missing.append("patient_instructions")
    if not any(
        getattr(record, field).strip()
        for field in ("recommendations", "treatment_plan", "follow_up_plan", "physical_visit_reason")
    ):
        missing.append("recommendation_or_plan")
    blocking = []
    if record.consultation.status in {
        ConsultationStatus.COMPLETED,
        ConsultationStatus.CANCELLED,
    }:
        blocking.append("consultation_terminal")
    return RecordValidation(
        can_finalize=not missing and not blocking and record.status == RecordStatus.DRAFT,
        missing_fields=missing,
        warnings=[],
        blocking_errors=blocking,
    )


def _validate_assignment(consultation: Consultation, doctor: DoctorProfile) -> None:
    if consultation.doctor_id != doctor.id:
        raise MedicalRecordWorkflowError("consultation_not_assigned", http_status=403)
    if not (
        doctor.user.is_active
        and doctor.is_approved
        and doctor.approval_status == DoctorProfile.ApprovalStatus.APPROVED
    ):
        raise MedicalRecordWorkflowError("approval_required", http_status=403)


def _fingerprint(action: str, payload: dict) -> str:
    canonical = json.dumps(
        {"action": action, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _existing_action(actor, client_request_id, action, fingerprint):
    existing = MedicalRecordAction.objects.select_related("record").filter(
        actor=actor,
        client_request_id=client_request_id,
    ).first()
    if existing and (
        existing.action != action or existing.request_fingerprint != fingerprint
    ):
        raise MedicalRecordWorkflowError("client_request_id_conflict")
    return existing


def _audit(record, actor, event_type: str, *, metadata: dict, request_id: str = ""):
    create_audit_event(
        event_type,
        AuditEventCategory.CONSULTATION,
        actor_id=str(actor.id),
        actor_role=actor.role,
        target_type="medical_record",
        target_id=str(record.id),
        request_id=request_id,
        metadata={"consultation_id": str(record.consultation_id), **metadata},
    )


def get_or_create_record(
    *, consultation_id, doctor, actor, client_request_id, request_id=""
):
    fingerprint = _fingerprint("create", {"consultation_id": consultation_id})
    with transaction.atomic():
        existing_action = _existing_action(
            actor, client_request_id, "create", fingerprint
        )
        if existing_action:
            return existing_action.record, False
        consultation = Consultation.objects.select_for_update(of=("self",)).select_related(
            "doctor__user", "patient__user", "specialty", "intake_session"
        ).get(pk=consultation_id)
        _validate_assignment(consultation, doctor)
        existing = MedicalRecordDraft.objects.select_for_update().filter(
            consultation=consultation
        ).first()
        if existing:
            if existing.created_by_id is None:
                existing.created_by = actor
                existing.save(update_fields=["created_by", "updated_at"])
            MedicalRecordAction.objects.create(
                record=existing,
                actor=actor,
                action="create",
                client_request_id=client_request_id,
                request_fingerprint=fingerprint,
                result_version=existing.version,
            )
            return existing, False
        if consultation.status not in CREATE_ALLOWED_STATUSES:
            code = (
                "consultation_terminal"
                if consultation.status in {ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED}
                else "record_creation_not_allowed"
            )
            raise MedicalRecordWorkflowError(code)

        try:
            intake = consultation.intake_session
        except AttributeError:
            intake = None
        collected = intake.collected_data if intake and isinstance(intake.collected_data, dict) else {}
        record = MedicalRecordDraft.objects.create(
            consultation=consultation,
            intake_session=intake,
            created_by=actor,
            chief_complaint=consultation.description.strip(),
            symptoms=collected.get("symptoms") or [],
            duration=collected.get("symptom_duration") or "",
            medications=collected.get("current_medications") or [],
            allergies=collected.get("allergies") or [],
            past_medical_history="\n".join(collected.get("chronic_conditions") or []),
            family_history="\n".join(collected.get("family_history") or []),
            provenance={
                "chief_complaint": "patient_reported",
                "symptoms": "intake_extracted",
                "duration": "intake_extracted",
                "medications": "intake_extracted",
                "allergies": "intake_extracted",
                "past_medical_history": "intake_extracted",
                "family_history": "intake_extracted",
            },
        )
        MedicalRecordAction.objects.create(
            record=record,
            actor=actor,
            action="create",
            client_request_id=client_request_id,
            request_fingerprint=fingerprint,
            result_version=record.version,
        )
        _audit(
            record,
            actor,
            "doctor_medical_record_created",
            metadata={"version": record.version, "source": "doctor_command"},
            request_id=request_id,
        )
        return record, True


def update_record(
    *, record_id, doctor, actor, values, expected_version, client_request_id, request_id=""
):
    normalized = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in values.items()
    }
    fingerprint = _fingerprint(
        "update",
        {"record_id": record_id, "expected_version": expected_version, "values": normalized},
    )
    with transaction.atomic():
        existing_action = _existing_action(
            actor, client_request_id, "update", fingerprint
        )
        if existing_action:
            return existing_action.record, False
        record = MedicalRecordDraft.objects.select_for_update().select_related(
            "consultation__doctor__user"
        ).get(pk=record_id)
        _validate_assignment(record.consultation, doctor)
        if record.status == RecordStatus.FINALIZED:
            raise MedicalRecordWorkflowError("medical_record_finalized")
        if record.version != expected_version:
            raise MedicalRecordWorkflowError("stale_medical_record")

        changed = []
        for field, value in normalized.items():
            if field not in DOCTOR_AUTHORED_FIELDS:
                raise MedicalRecordWorkflowError("field_not_editable", http_status=400)
            if isinstance(value, str) and len(value) > 5000:
                raise MedicalRecordWorkflowError(
                    "validation_failed", http_status=400, details={field: "max_length"}
                )
            if getattr(record, field) != value:
                setattr(record, field, value)
                changed.append(field)
        if changed:
            record.version += 1
            record.provenance = {
                **record.provenance,
                **{field: "doctor_authored" for field in changed},
            }
            record.save(update_fields=[*changed, "version", "provenance", "updated_at"])
        MedicalRecordAction.objects.create(
            record=record,
            actor=actor,
            action="update",
            client_request_id=client_request_id,
            request_fingerprint=fingerprint,
            result_version=record.version,
        )
        if changed:
            _audit(
                record,
                actor,
                "doctor_medical_record_updated",
                metadata={"changed_fields": changed, "version": record.version},
                request_id=request_id,
            )
        return record, bool(changed)


def finalize_record(
    *, record_id, doctor, actor, expected_version, client_request_id, confirmation, request_id=""
):
    if confirmation is not True:
        raise MedicalRecordWorkflowError("confirmation_required", http_status=400)
    fingerprint = _fingerprint(
        "finalize",
        {"record_id": record_id, "expected_version": expected_version, "confirmation": True},
    )
    with transaction.atomic():
        existing_action = _existing_action(
            actor, client_request_id, "finalize", fingerprint
        )
        if existing_action:
            return existing_action.record, False
        record_ref = MedicalRecordDraft.objects.only("consultation_id").get(pk=record_id)
        consultation = Consultation.objects.select_for_update(of=("self",)).get(
            pk=record_ref.consultation_id
        )
        record = MedicalRecordDraft.objects.select_for_update().select_related(
            "consultation__doctor__user", "consultation__patient__user"
        ).get(pk=record_id)
        if record.consultation_id != consultation.id:
            raise MedicalRecordWorkflowError("stale_medical_record")
        record.consultation = consultation
        _validate_assignment(consultation, doctor)
        if record.status == RecordStatus.FINALIZED:
            raise MedicalRecordWorkflowError("medical_record_finalized")
        if record.version != expected_version:
            raise MedicalRecordWorkflowError("stale_medical_record")
        validation = validate_record_for_finalization(record)
        if not validation.can_finalize:
            raise MedicalRecordWorkflowError(
                "validation_failed",
                http_status=400,
                details={
                    "missing_fields": validation.missing_fields,
                    "blocking_errors": validation.blocking_errors,
                },
            )
        record.status = RecordStatus.FINALIZED
        record.finalized_at = timezone.now()
        record.finalized_by = actor
        record.version += 1
        record.save(
            update_fields=["status", "finalized_at", "finalized_by", "version", "updated_at"]
        )
        MedicalRecordAction.objects.create(
            record=record,
            actor=actor,
            action="finalize",
            client_request_id=client_request_id,
            request_fingerprint=fingerprint,
            result_version=record.version,
        )
        Notification.objects.get_or_create(
            recipient=consultation.patient.user,
            notification_type=NotificationType.RECORD_FINALIZED,
            consultation=consultation,
            defaults={
                "title": "Medical record available",
                "body": "A finalized medical record is available.",
            },
        )
        _audit(
            record,
            actor,
            "doctor_medical_record_finalized",
            metadata={"version": record.version, "patient_visible": True},
            request_id=request_id,
        )
        return record, True
