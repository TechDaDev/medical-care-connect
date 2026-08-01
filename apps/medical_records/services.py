"""Service for generating and managing medical record drafts."""

import logging

from apps.medical_records.models import MedicalRecordDraft

logger = logging.getLogger(__name__)

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
    """Create intake-derived draft once; never overwrite later clinical work."""
    consultation = intake_session.consultation
    collected = intake_session.collected_data or {}

    defaults = {
        "intake_session": intake_session,
        "status": "draft",
        "provenance": {},
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
        defaults["provenance"][dst_key] = "intake_extracted"

    record, created = MedicalRecordDraft.objects.get_or_create(
        consultation=consultation,
        defaults=defaults,
    )

    if created:
        logger.info(
            "Created draft record %s for consultation %s",
            record.id, consultation.id,
        )
    return record
