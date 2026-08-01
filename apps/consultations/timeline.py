from apps.consultations.models import ConsultationStatus


BASE_STEPS = [
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.INTAKE_IN_PROGRESS,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.COMPLETED,
]
BRANCH_AFTER = {
    ConsultationStatus.AWAITING_PATIENT_RESPONSE: ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE: ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.UNDER_REVIEW: ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.FOLLOW_UP_REQUIRED: ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.PHYSICAL_VISIT_REQUIRED: ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.TRANSFERRED: ConsultationStatus.ACCEPTED,
    ConsultationStatus.EMERGENCY_ESCALATED: ConsultationStatus.INTAKE_IN_PROGRESS,
}
TERMINAL = {
    ConsultationStatus.COMPLETED,
    ConsultationStatus.CANCELLED,
    ConsultationStatus.EMERGENCY_ESCALATED,
}


def build_patient_timeline(consultation) -> list[dict]:
    current = consultation.status
    steps = list(BASE_STEPS)
    if current == ConsultationStatus.CANCELLED:
        steps = [ConsultationStatus.SUBMITTED, ConsultationStatus.CANCELLED]
    elif current in BRANCH_AFTER:
        anchor = BRANCH_AFTER[current]
        steps.insert(steps.index(anchor) + 1, current)

    if current not in steps:
        steps.append(current)
    current_index = steps.index(current)
    timestamps = {
        ConsultationStatus.SUBMITTED: consultation.submitted_at,
        ConsultationStatus.ACCEPTED: consultation.accepted_at,
        ConsultationStatus.CANCELLED: consultation.cancelled_at,
    }
    output = []
    for index, key in enumerate(steps):
        if key in TERMINAL and key == current:
            state = "terminal" if key != ConsultationStatus.COMPLETED else "current"
        elif index < current_index:
            state = "completed"
        elif index == current_index:
            state = "current"
        else:
            state = "upcoming"
        occurred_at = timestamps.get(key)
        if occurred_at is None and index == current_index:
            occurred_at = consultation.updated_at
        output.append(
            {
                "key": key,
                "status": state,
                "occurred_at": occurred_at,
                "title_key": f"consultation.timeline.{key}.title",
                "description_key": f"consultation.timeline.{key}.description",
            }
        )
    return output


def build_doctor_timeline(consultation) -> list[dict]:
    """Build lifecycle timeline from authoritative state and action events."""
    timestamps = {
        ConsultationStatus.SUBMITTED: consultation.submitted_at,
        ConsultationStatus.ACCEPTED: consultation.accepted_at,
        ConsultationStatus.COMPLETED: consultation.completed_at,
        ConsultationStatus.CANCELLED: consultation.cancelled_at,
    }
    try:
        events = list(consultation.doctor_actions.all())
    except (AttributeError, TypeError):
        events = []
    for event in events:
        timestamps[event.new_status] = event.created_at

    current = consultation.status
    if current == ConsultationStatus.CANCELLED:
        steps = [ConsultationStatus.SUBMITTED, ConsultationStatus.CANCELLED]
    else:
        steps = list(BASE_STEPS)
        event_states = [event.new_status for event in events]
        for state in event_states:
            if state in steps:
                continue
            anchor = BRANCH_AFTER.get(state, ConsultationStatus.DOCTOR_REVIEW)
            steps.insert(steps.index(anchor) + 1, state)
        if current not in steps:
            anchor = BRANCH_AFTER.get(current)
            if anchor in steps:
                steps.insert(steps.index(anchor) + 1, current)
            else:
                steps.append(current)

    current_index = steps.index(current)
    output = []
    for index, key in enumerate(steps):
        if key in TERMINAL and key == current:
            state = "terminal" if key != ConsultationStatus.COMPLETED else "current"
        elif index < current_index:
            state = "completed"
        elif index == current_index:
            state = "current"
        else:
            state = "upcoming"
        occurred_at = timestamps.get(key)
        if occurred_at is None and index == current_index:
            occurred_at = consultation.updated_at
        output.append({
            "key": key,
            "status": state,
            "occurred_at": occurred_at,
            "title_key": f"consultation.timeline.{key}.title",
            "description_key": f"consultation.timeline.{key}.description",
        })
    return output
