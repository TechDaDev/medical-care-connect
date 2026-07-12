"""Service for generating and managing medical record drafts."""

import logging

from django.utils import timezone

from apps.medical_records.models import MedicalRecordDraft

logger = logging.getLogger(__name__)

# Map intake collected_data keys → MedicalRecordDraft fields
_FIELD_MAP = {
    "chief_complaint": "chief_complaint",
    "symptoms": "symptoms",
    "severity": "severity",
    "duration": "duration",
    "location": "location",
    "triggers": "triggers",
    "relieving_factors": "relieving_factors",
    "past_medical_history": "past_medical_history",
    "medications": "medications",
    "allergies": "allergies",
    "family_history": "family_history",
    "social_history": "social_history",
    "additional_notes": "additional_notes",
}

# Map from CollectedData schema fields (snake_case in schemas.py)
_COLLECTED_MAP = {
    "chief_complaint": "chief_complaint",
    "symptoms": "symptoms",
    "severity": "severity",
    "symptom_duration": "duration",
    "location": "location",
    "associated_symptoms": "symptoms",
    "chronic_conditions": "past_medical_history",
    "current_medications": "medications",
    "allergies": "allergies",
    "surgical_history": "past_medical_history",
    "family_history": "family_history",
    "additional_information": "additional_notes",
}


def generate_draft_from_intake(intake_session) -> MedicalRecordDraft:
    """Create or update a MedicalRecordDraft from a completed intake session."""
    consultation = intake_session.consultation
    collected = intake_session.collected_data or {}

    defaults = {
        "intake_session": intake_session,
        "status": "draft",
    }

    # Map collected data fields
    for src_key, dst_key in _COLLECTED_MAP.items():
        value = collected.get(src_key)
        if value is None:
            continue

        existing = defaults.get(dst_key)
        if dst_key in ("symptoms",) and isinstance(value, list):
            # Merge symptom lists
            merged = list(set(
                (existing or []) + value
            ))
            defaults[dst_key] = merged
        elif dst_key in ("medications", "allergies") and isinstance(value, list):
            merged = list(set(
                (existing or []) + value
            ))
            defaults[dst_key] = merged
        elif isinstance(value, str):
            existing_str = existing or ""
            if value not in existing_str:
                defaults[dst_key] = (
                    (existing_str + "\n" + value) if existing_str else value
                )
        else:
            defaults[dst_key] = value

    # Build HPI from complaint + duration
    hpi_parts = []
    cc = defaults.get("chief_complaint", "")
    if cc:
        hpi_parts.append(f"Patient presents with {cc.lower().rstrip('.')}.")
    duration = defaults.get("duration", "")
    if duration:
        hpi_parts.append(f"Duration: {duration}.")
    if hpi_parts:
        defaults["history_of_present_illness"] = " ".join(hpi_parts)

    record, created = MedicalRecordDraft.objects.update_or_create(
        consultation=consultation,
        defaults=defaults,
    )

    if created:
        logger.info(
            "Created draft record %s for consultation %s",
            record.id, consultation.id,
        )
    else:
        logger.info(
            "Updated draft record %s for consultation %s",
            record.id, consultation.id,
        )

    return record
