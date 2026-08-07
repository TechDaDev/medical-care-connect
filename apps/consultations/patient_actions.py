from dataclasses import dataclass

from apps.consultations.models import ConsultationStatus


PATIENT_CANCELLABLE = {
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.INTAKE_IN_PROGRESS,
}
MESSAGING_ALLOWED = {
    ConsultationStatus.SUBMITTED,
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
ATTACHMENT_CLOSED = {
    ConsultationStatus.COMPLETED,
    ConsultationStatus.CANCELLED,
    ConsultationStatus.EMERGENCY_ESCALATED,
}


@dataclass(frozen=True)
class PatientActionPolicy:
    actions: dict[str, bool]
    reasons: dict[str, str | None]

    @property
    def available_actions(self) -> list[str]:
        mapping = {
            "can_continue_intake": "continue_intake",
            "can_start_intake": "start_intake",
            "can_message": "message",
            "can_cancel": "cancel",
            "can_view_record": "view_record",
            "can_write_review": "write_review",
            "can_upload_attachment": "upload_attachment",
        }
        return ["view"] + [
            action for flag, action in mapping.items() if self.actions[flag]
        ]


def patient_action_policy(consultation) -> PatientActionPolicy:
    intake = getattr(consultation, "intake_session", None)
    record = getattr(consultation, "medical_record", None)
    review = getattr(consultation, "review", None)
    terminal = consultation.status in {
        ConsultationStatus.COMPLETED,
        ConsultationStatus.CANCELLED,
    }
    emergency = consultation.status == ConsultationStatus.EMERGENCY_ESCALATED
    intake_active = bool(
        intake and intake.status in {"not_started", "in_progress", "awaiting_patient_review"}
    )
    intake_complete = bool(
        intake and intake.status in {"awaiting_patient_review", "confirmed", "submitted_to_doctor"}
    )

    actions = {
        "can_cancel": consultation.status in PATIENT_CANCELLABLE,
        "can_message": consultation.status in MESSAGING_ALLOWED,
        "can_start_intake": (
            consultation.status == ConsultationStatus.ACCEPTED and intake is None
        ),
        "can_continue_intake": (
            consultation.status
            in {ConsultationStatus.ACCEPTED, ConsultationStatus.INTAKE_IN_PROGRESS}
            and intake_active
        ),
        "can_view_record": bool(record),
        "can_write_review": (
            consultation.status == ConsultationStatus.COMPLETED and review is None
        ),
        "can_upload_attachment": consultation.status not in ATTACHMENT_CLOSED,
    }

    def reason(flag: str, unavailable: str) -> str | None:
        if actions[flag]:
            return None
        if emergency:
            return "emergency_escalated"
        if terminal:
            return "terminal_consultation"
        return unavailable

    reasons = {
        "cancel": reason("can_cancel", "cancellation_not_allowed"),
        "message": reason("can_message", "message_unavailable"),
        "intake": (
            None
            if actions["can_start_intake"] or actions["can_continue_intake"]
            else (
                "intake_already_complete"
                if intake_complete
                else "awaiting_doctor"
            )
        ),
        "record": reason("can_view_record", "no_medical_record"),
        "review": reason("can_write_review", "review_not_available"),
        "attachment": reason(
            "can_upload_attachment", "attachment_upload_closed"
        ),
    }
    return PatientActionPolicy(actions=actions, reasons=reasons)
