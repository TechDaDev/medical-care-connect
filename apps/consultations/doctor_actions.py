"""Authoritative doctor consultation workflow policy and mutations."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.consultations.models import (
    Consultation,
    ConsultationStatus,
    ConsultationTransfer,
    DoctorConsultationAction,
)
from apps.core.audit_service import create_audit_event
from apps.core.models import AuditEventCategory
from apps.doctors.models import DoctorProfile
from apps.messaging.services import consultation_allows_messaging
from apps.medical_records.models import ClinicalOutcome, MedicalRecordDraft, RecordStatus
from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification


TERMINAL_STATUSES = {
    ConsultationStatus.COMPLETED,
    ConsultationStatus.CANCELLED,
}

DOCTOR_ACTION_STATUSES = {
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
    ConsultationStatus.UNDER_REVIEW,
    ConsultationStatus.FOLLOW_UP_REQUIRED,
    ConsultationStatus.EMERGENCY_ESCALATED,
}

STATUS_GROUPS = {
    "new_requests": {ConsultationStatus.SUBMITTED},
    "needs_action": DOCTOR_ACTION_STATUSES,
    "active": {
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
        ConsultationStatus.EMERGENCY_ESCALATED,
    },
    "awaiting_patient": {ConsultationStatus.AWAITING_PATIENT_RESPONSE},
    "completed": {ConsultationStatus.COMPLETED},
    "cancelled": {ConsultationStatus.CANCELLED},
    "terminal": TERMINAL_STATUSES,
}

TRANSITIONS = {
    "begin_review": {
        ConsultationStatus.INTAKE_COMPLETED: ConsultationStatus.DOCTOR_REVIEW,
        ConsultationStatus.AWAITING_DOCTOR_RESPONSE: ConsultationStatus.UNDER_REVIEW,
    },
    "request_patient_response": {
        ConsultationStatus.DOCTOR_REVIEW: ConsultationStatus.AWAITING_PATIENT_RESPONSE,
        ConsultationStatus.UNDER_REVIEW: ConsultationStatus.AWAITING_PATIENT_RESPONSE,
    },
    "mark_awaiting_doctor": {
        ConsultationStatus.AWAITING_DOCTOR_RESPONSE: ConsultationStatus.UNDER_REVIEW,
    },
    "require_follow_up": {
        ConsultationStatus.DOCTOR_REVIEW: ConsultationStatus.FOLLOW_UP_REQUIRED,
        ConsultationStatus.UNDER_REVIEW: ConsultationStatus.FOLLOW_UP_REQUIRED,
    },
    "require_physical_visit": {
        ConsultationStatus.DOCTOR_REVIEW: ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
        ConsultationStatus.UNDER_REVIEW: ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
    },
    "transfer": {
        status: ConsultationStatus.TRANSFERRED
        for status in ConsultationStatus.values
        if status not in TERMINAL_STATUSES | {ConsultationStatus.EMERGENCY_ESCALATED}
    },
    "complete": {
        ConsultationStatus.DOCTOR_REVIEW: ConsultationStatus.COMPLETED,
        ConsultationStatus.UNDER_REVIEW: ConsultationStatus.COMPLETED,
        ConsultationStatus.FOLLOW_UP_REQUIRED: ConsultationStatus.COMPLETED,
        ConsultationStatus.PHYSICAL_VISIT_REQUIRED: ConsultationStatus.COMPLETED,
    },
    "emergency_escalate": {
        ConsultationStatus.DOCTOR_REVIEW: ConsultationStatus.EMERGENCY_ESCALATED,
        ConsultationStatus.UNDER_REVIEW: ConsultationStatus.EMERGENCY_ESCALATED,
        ConsultationStatus.FOLLOW_UP_REQUIRED: ConsultationStatus.EMERGENCY_ESCALATED,
        ConsultationStatus.PHYSICAL_VISIT_REQUIRED: ConsultationStatus.EMERGENCY_ESCALATED,
    },
}

REASON_REQUIRED = {
    "request_patient_response",
    "require_follow_up",
    "require_physical_visit",
    "transfer",
    "complete",
    "emergency_escalate",
}

ACTION_OUTCOMES = {
    "complete": ClinicalOutcome.REMOTE_CARE_COMPLETED,
    "require_follow_up": ClinicalOutcome.FOLLOW_UP_REQUIRED,
    "require_physical_visit": ClinicalOutcome.PHYSICAL_VISIT_REQUIRED,
    "transfer": ClinicalOutcome.TRANSFERRED,
    "emergency_escalate": ClinicalOutcome.EMERGENCY_ESCALATED,
}


@dataclass(frozen=True)
class DoctorActionPolicy:
    actions: dict[str, bool]
    reasons: dict[str, str | None]
    available_actions: list[str]
    needs_doctor_action: bool
    doctor_action_type: str | None


class DoctorWorkflowError(Exception):
    def __init__(self, code: str, *, http_status: int = 409):
        self.code = code
        self.http_status = http_status
        super().__init__(code)


def _has_related(instance, name: str) -> bool:
    try:
        return getattr(instance, name, None) is not None
    except AttributeError:
        return False


def doctor_action_policy(consultation: Consultation, doctor=None) -> DoctorActionPolicy:
    assigned = doctor is None or consultation.doctor_id == getattr(doctor, "id", None)
    approved = bool(
        doctor is None
        or (
            doctor.user.is_active
            and doctor.is_approved
            and doctor.approval_status == DoctorProfile.ApprovalStatus.APPROVED
        )
    )
    terminal = consultation.status in TERMINAL_STATUSES
    intake_complete = bool(
        _has_related(consultation, "intake_session")
        and consultation.intake_session.status in {"ready_for_review", "confirmed"}
    )
    record_exists = _has_related(consultation, "medical_record")
    record_finalized = bool(
        record_exists and consultation.medical_record.status == RecordStatus.FINALIZED
    )

    base_allowed = assigned and approved and not terminal
    actions = {
        "can_accept": base_allowed and consultation.status == ConsultationStatus.SUBMITTED,
        "can_message": base_allowed and consultation_allows_messaging(consultation),
        "can_review_intake": base_allowed and intake_complete,
        "can_request_patient_response": base_allowed and consultation.status in {
            ConsultationStatus.DOCTOR_REVIEW, ConsultationStatus.UNDER_REVIEW,
        },
        "can_mark_awaiting_doctor": base_allowed
        and consultation.status == ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
        "can_begin_review": base_allowed and consultation.status in {
            ConsultationStatus.INTAKE_COMPLETED,
            ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
        },
        "can_require_follow_up": base_allowed and record_finalized and consultation.status in {
            ConsultationStatus.DOCTOR_REVIEW, ConsultationStatus.UNDER_REVIEW,
        },
        "can_require_physical_visit": base_allowed and record_finalized and consultation.status in {
            ConsultationStatus.DOCTOR_REVIEW, ConsultationStatus.UNDER_REVIEW,
        },
        "can_transfer": base_allowed and record_finalized
        and consultation.status != ConsultationStatus.EMERGENCY_ESCALATED,
        "can_emergency_escalate": base_allowed
        and record_finalized
        and consultation.status in TRANSITIONS["emergency_escalate"],
        "can_complete": base_allowed
        and consultation.status in TRANSITIONS["complete"]
        and record_finalized
        and consultation.status != ConsultationStatus.AWAITING_PATIENT_RESPONSE,
        "can_add_internal_note": assigned and approved,
        "can_upload_attachment": base_allowed
        and consultation.status != ConsultationStatus.EMERGENCY_ESCALATED,
        "can_view_record_summary": assigned and approved and record_exists,
    }

    def reason(action: str) -> str | None:
        if not assigned:
            return "not_assigned_doctor"
        if not approved:
            return "approval_required"
        if terminal:
            return "terminal_consultation"
        if action == "accept" and consultation.status != ConsultationStatus.SUBMITTED:
            return "consultation_not_submitted"
        if action in {"review_intake", "begin_review"} and not intake_complete:
            return "intake_not_complete"
        if action in {"complete", "follow_up", "physical_visit", "transfer", "emergency_escalate"} and not record_exists:
            return "medical_record_required"
        if action in {"complete", "follow_up", "physical_visit", "transfer", "emergency_escalate"} and not record_finalized:
            return "medical_record_not_finalized"
        if consultation.status == ConsultationStatus.AWAITING_PATIENT_RESPONSE:
            return "awaiting_patient"
        if consultation.status == ConsultationStatus.EMERGENCY_ESCALATED:
            return "emergency_escalated"
        return "action_not_available"

    key_map = {
        "accept": "can_accept",
        "message": "can_message",
        "review_intake": "can_review_intake",
        "request_patient_response": "can_request_patient_response",
        "mark_awaiting_doctor": "can_mark_awaiting_doctor",
        "begin_review": "can_begin_review",
        "follow_up": "can_require_follow_up",
        "physical_visit": "can_require_physical_visit",
        "transfer": "can_transfer",
        "emergency_escalate": "can_emergency_escalate",
        "complete": "can_complete",
        "internal_note": "can_add_internal_note",
        "attachment": "can_upload_attachment",
        "record_summary": "can_view_record_summary",
    }
    reasons = {
        key: None if actions[value] else reason(key)
        for key, value in key_map.items()
    }
    available = ["view"]
    available.extend(key for key, value in key_map.items() if actions[value])

    action_type = None
    if consultation.status == ConsultationStatus.EMERGENCY_ESCALATED:
        action_type = "emergency"
    elif consultation.status == ConsultationStatus.SUBMITTED:
        action_type = "new_request"
    elif consultation.status == ConsultationStatus.INTAKE_COMPLETED:
        action_type = "review_intake"
    elif consultation.status == ConsultationStatus.AWAITING_DOCTOR_RESPONSE:
        action_type = "reply_to_patient"
    elif consultation.status in {ConsultationStatus.DOCTOR_REVIEW, ConsultationStatus.UNDER_REVIEW}:
        action_type = "clinical_review"
    elif consultation.status == ConsultationStatus.FOLLOW_UP_REQUIRED:
        action_type = "follow_up"

    return DoctorActionPolicy(
        actions=actions,
        reasons=reasons,
        available_actions=available,
        needs_doctor_action=consultation.status in DOCTOR_ACTION_STATUSES,
        doctor_action_type=action_type,
    )


def _validate_assignment(consultation: Consultation, doctor) -> None:
    if consultation.doctor_id != doctor.id:
        raise DoctorWorkflowError("consultation_not_assigned", http_status=403)
    if not (
        doctor.user.is_active
        and doctor.is_approved
        and doctor.approval_status == DoctorProfile.ApprovalStatus.APPROVED
    ):
        raise DoctorWorkflowError("approval_required", http_status=403)


def _validate_expected(consultation, expected_status, expected_updated_at) -> None:
    if expected_status and consultation.status != expected_status:
        raise DoctorWorkflowError("consultation_state_changed")
    if expected_updated_at is not None and consultation.updated_at != expected_updated_at:
        raise DoctorWorkflowError("stale_consultation")


def _notify_transition(consultation, action: str, target_doctor=None) -> None:
    patient_actions = {
        "accept": "Consultation accepted",
        "request_patient_response": "Doctor requested more information",
        "require_follow_up": "Follow-up required",
        "require_physical_visit": "Physical visit required",
        "transfer": "Consultation transferred",
        "complete": "Consultation completed",
        "emergency_escalate": "Emergency guidance available",
    }
    if action in patient_actions:
        create_notification(
            recipient=consultation.patient.user,
            notification_type=(
                NotificationType.CONSULTATION_ACCEPTED
                if action == "accept"
                else NotificationType.STATUS_CHANGE
            ),
            title=patient_actions[action],
            body="Consultation status was updated.",
            consultation=consultation,
        )
    if action == "transfer" and target_doctor is not None:
        create_notification(
            recipient=target_doctor.user,
            notification_type=NotificationType.NEW_CONSULTATION,
            title="Transferred consultation",
            body="A consultation was assigned to you.",
            consultation=consultation,
        )


def perform_doctor_action(
    *,
    consultation_id,
    doctor,
    actor,
    action: str,
    client_request_id,
    expected_status: str | None,
    expected_updated_at,
    reason: str = "",
    target_doctor_id=None,
    outcome: str | None = None,
    medical_record_id=None,
    confirmation: bool | None = None,
    request_id: str = "",
) -> tuple[Consultation, bool]:
    """Apply one allowlisted doctor action under row lock."""
    if action != "accept" and action not in TRANSITIONS:
        raise DoctorWorkflowError("action_not_available", http_status=400)

    with transaction.atomic():
        existing = DoctorConsultationAction.objects.filter(
            actor=actor, client_request_id=client_request_id
        ).select_related("consultation").first()
        if existing:
            if existing.consultation_id != consultation_id or existing.action != action:
                raise DoctorWorkflowError("client_request_id_conflict")
            consultation = Consultation.objects.select_related(
                "patient__user", "doctor__user", "doctor__specialty", "specialty",
                "intake_session", "medical_record",
            ).get(pk=existing.consultation_id)
            return consultation, False

        consultation = Consultation.objects.select_for_update(of=("self",)).select_related(
            "patient__user", "doctor__user", "doctor__specialty", "specialty",
            "intake_session", "medical_record",
        ).get(pk=consultation_id)
        _validate_assignment(consultation, doctor)
        _validate_expected(consultation, expected_status, expected_updated_at)

        old_status = consultation.status
        if action == "accept":
            if old_status != ConsultationStatus.SUBMITTED:
                code = {
                    ConsultationStatus.ACCEPTED: "consultation_already_accepted",
                    ConsultationStatus.CANCELLED: "consultation_cancelled",
                    ConsultationStatus.COMPLETED: "consultation_completed",
                }.get(old_status, "consultation_state_changed")
                raise DoctorWorkflowError(code)
            new_status = ConsultationStatus.ACCEPTED
        else:
            new_status = TRANSITIONS[action].get(old_status)
            if new_status is None:
                code = (
                    "consultation_completed" if old_status == ConsultationStatus.COMPLETED
                    else "consultation_cancelled" if old_status == ConsultationStatus.CANCELLED
                    else "emergency_escalated" if old_status == ConsultationStatus.EMERGENCY_ESCALATED
                    else "action_not_available"
                )
                raise DoctorWorkflowError(code)

        normalized_reason = " ".join(reason.split())
        if action in REASON_REQUIRED and len(normalized_reason) < 10:
            raise DoctorWorkflowError("reason_required", http_status=400)
        if len(normalized_reason) > 1000:
            raise DoctorWorkflowError("reason_too_long", http_status=400)

        target_doctor = None
        if action == "transfer":
            if not target_doctor_id:
                raise DoctorWorkflowError("target_doctor_required", http_status=400)
            target_doctor = DoctorProfile.objects.select_related("user", "specialty").filter(
                pk=target_doctor_id,
                is_approved=True,
                approval_status=DoctorProfile.ApprovalStatus.APPROVED,
                user__is_active=True,
            ).first()
            if target_doctor is None or target_doctor.id == doctor.id:
                raise DoctorWorkflowError("target_doctor_ineligible", http_status=400)
            if consultation.specialty_id and target_doctor.specialty_id != consultation.specialty_id:
                raise DoctorWorkflowError("target_doctor_specialty_mismatch", http_status=400)

        record = None
        if action in ACTION_OUTCOMES:
            if not medical_record_id:
                raise DoctorWorkflowError("medical_record_required")
            record = MedicalRecordDraft.objects.select_for_update().filter(
                pk=medical_record_id,
                consultation=consultation,
            ).first()
            if record is None:
                raise DoctorWorkflowError("medical_record_not_found", http_status=404)
            if record.status != RecordStatus.FINALIZED:
                raise DoctorWorkflowError("medical_record_not_finalized")
            if confirmation is not True:
                raise DoctorWorkflowError("confirmation_required", http_status=400)
            expected_outcome = ACTION_OUTCOMES[action]
            if outcome != expected_outcome:
                raise DoctorWorkflowError("outcome_action_mismatch", http_status=400)

        now = timezone.now()
        consultation.status = new_status
        update_fields = ["status", "updated_at"]
        if action == "accept":
            consultation.accepted_at = now
            update_fields.append("accepted_at")
        if action == "complete":
            consultation.completed_at = now
            update_fields.append("completed_at")
        if action == "transfer":
            previous_doctor = consultation.doctor
            consultation.doctor = target_doctor
            consultation.specialty = target_doctor.specialty
            update_fields.extend(["doctor", "specialty"])
            ConsultationTransfer.objects.create(
                consultation=consultation,
                previous_doctor=previous_doctor,
                new_doctor=target_doctor,
                transferred_by=actor,
                reason=normalized_reason,
            )
        consultation.save(update_fields=update_fields)
        if record is not None:
            record.clinical_outcome = outcome
            record.outcome_recorded_at = now
            record.save(update_fields=["clinical_outcome", "outcome_recorded_at", "updated_at"])

        DoctorConsultationAction.objects.create(
            consultation=consultation,
            actor=actor,
            action=action,
            old_status=old_status,
            new_status=new_status,
            reason=normalized_reason,
            target_doctor=target_doctor,
            client_request_id=client_request_id,
        )
        _notify_transition(consultation, action, target_doctor)
        create_audit_event(
            f"doctor_consultation_{action}",
            AuditEventCategory.CONSULTATION,
            actor_id=str(actor.id),
            actor_role=actor.role,
            target_type="consultation",
            target_id=str(consultation.id),
            request_id=request_id,
            metadata={
                "action": action,
                "old_status": old_status,
                "new_status": new_status,
                "reason_present": bool(normalized_reason),
                "target_doctor_id": str(target_doctor.id) if target_doctor else None,
                "outcome": outcome,
                "medical_record_id": str(record.id) if record else None,
            },
        )
        return consultation, True
