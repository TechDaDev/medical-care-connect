"""Intake session state machine — centralized legal transitions.

The frontend and DeepSeek must never write arbitrary status values.
Every status change goes through transition_state().
"""

import logging

from apps.ai_intake.models import IntakeSessionStatus

logger = logging.getLogger(__name__)

# Recommended Phase A states. Kept compatible with the existing model:
# awaiting_patient removed; awaiting_patient_review added; submitted_to_doctor,
# correction_in_progress, temporarily_unavailable, cancelled added.
STATE_CHOICES = {
    "not_started": "not_started",
    "in_progress": "in_progress",
    "awaiting_patient_review": "awaiting_patient_review",
    "correction_in_progress": "correction_in_progress",
    "confirmed": "confirmed",
    "submitted_to_doctor": "submitted_to_doctor",
    "emergency_stopped": "emergency_stopped",
    "temporarily_unavailable": "temporarily_unavailable",
    "failed": "failed",
    "cancelled": "cancelled",
}

TRANSITIONS: dict[str, set[str]] = {
    "not_started": {"in_progress", "cancelled", "failed"},
    "in_progress": {
        "in_progress",  # same-state refresh unchanged
        "awaiting_patient_review",
        "correction_in_progress",
        "emergency_stopped",
        "temporarily_unavailable",
        "failed",
        "cancelled",
    },
    "awaiting_patient_review": {
        "correction_in_progress",
        "confirmed",
        "emergency_stopped",
        "cancelled",
    },
    "correction_in_progress": {
        "awaiting_patient_review",
        "in_progress",  # patient returned to questioning
        "emergency_stopped",
        "cancelled",
    },
    "confirmed": {
        "submitted_to_doctor",
        "correction_in_progress",  # disciplined undo before submission
        "cancelled",
    },
    "submitted_to_doctor": set(),  # terminal
    "emergency_stopped": set(),  # terminal
    "temporarily_unavailable": {
        "in_progress",  # safe retry back to normal questioning
        "failed",
        "cancelled",
    },
    "failed": {
        "in_progress",  # safe retry only via explicit recovery path
        "cancelled",
    },
    "cancelled": set(),  # terminal
}

REVIEWABLE_STATES = {"awaiting_patient_review", "correction_in_progress", "confirmed"}
CORRECTABLE_STATES = {"awaiting_patient_review", "correction_in_progress"}
CONFIRMABLE_STATES = {"awaiting_patient_review"}
ACTIVE_QUESTIONING_STATES = {"not_started", "in_progress"}
RETRYABLE_STATES = {"failed", "temporarily_unavailable"}
TERMINAL_STATES = {"submitted_to_doctor", "emergency_stopped", "cancelled"}


class IllegalTransition(Exception):
    pass


def is_known_state(status: str) -> bool:
    return status in STATE_CHOICES


def transition_state(session, new_status: str, *, audit_metadata: dict | None = None) -> bool:
    """Transition session status; returns True when status actually changed."""
    current = session.status
    if current == new_status:
        return False
    allowed = TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise IllegalTransition(
            f"Illegal intake state transition: {current} -> {new_status}"
        )
    return True


def legal_targets(status: str) -> list[str]:
    return sorted(TRANSITIONS.get(status, set()))