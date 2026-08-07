"""Service for generating and managing medical record drafts.

Phase A separation contract:
- patient-reported seed: populated ONLY from patient-confirmed intake
  values that the patient reported or explicitly accepted;
- AI-derived: labeled provenance (intake_extracted), never merged into
  doctor-authored fields;
- doctor-authored fields (assessment, working_diagnosis, treatment_plan,
  patient_instructions, recommendations, follow_up_plan, clinical_outcome):
  ALWAYS empty when generated from intake.
"""

import logging

from apps.medical_records.models import MedicalRecordDraft, RecordStatus

logger = logging.getLogger(__name__)

# Canonical draft fields the patient-reported seed may populate.
_PATIENT_REPORTED_MAP = {
    "chief_complaint": "chief_complaint",
    "symptoms": "symptoms",
    "duration": "duration",
    "location": "location",
    "triggers": "triggers",
    "relieving_factors": "relieving_factors",
    "past_medical_history": "past_medical_history",
    "medications": "medications",
    "allergies": "allergies",
    "family_history": "family_history",
    "social_history": "social_history",
    "warning_signs": "warning_signs",
}

# Doctor-authored fields that MUST remain empty on intake-derived drafts.
_DOCTOR_AUTHORED_FIELDS = [
    "history_of_present_illness",
    "review_of_systems",
    "doctor_notes",
    "clinical_summary",
    "assessment",
    "working_diagnosis",
    "differential_considerations",
    "recommendations",
    "treatment_plan",
    "follow_up_plan",
    "physical_visit_reason",
    "patient_instructions",
    "clinical_outcome",
]


def _merge_list(existing, value):
    if isinstance(value, list):
        return list(dict.fromkeys((existing or []) + [v for v in value if v]))
    if isinstance(value, str) and value:
        return list(dict.fromkeys((existing or []) + [value]))
    return existing or []


def _merge_text(existing, value):
    if not value:
        return existing or ""
    if isinstance(value, list):
        parts = [v for v in value if v]
        value = "\n".join(parts)
    existing_str = existing or ""
    if value and value not in existing_str:
        return (existing_str + "\n" + value).strip()
    return existing_str or ""


def generate_draft_from_intake(intake_session) -> MedicalRecordDraft:
    """Create intake-derived draft once; never overwrite later clinical work.

    Only called from the deterministic submit flow after patient confirmation.
    """
    consultation = intake_session.consultation
    collected = intake_session.collected_data or {}
    metadata = intake_session.field_metadata or {}

    defaults = {
        "status": RecordStatus.DRAFT,
        "intake_session": intake_session,
        "provenance": {},
        "version": 1,
    }

    provenance = {}
    for src_key, dst_key in _PATIENT_REPORTED_MAP.items():
        entry = metadata.get(src_key)
        value = entry.get("value") if entry else None
        if value is None or entry.get("status") != "answered":
            continue

        field_type = defaults.get(dst_key)
        if dst_key in {"symptoms", "medications", "allergies"}:
            merged = _merge_list(defaults.get(dst_key), value)
            if merged:
                defaults[dst_key] = merged
                provenance[dst_key] = {
                    "source": "patient_confirmed_intake",
                    "source_kind": entry.get("source", "intake_extraction"),
                    "confirmed_by_patient": entry.get("confirmed_by_patient", True),
                    "evidence_message_ids": entry.get("evidence_message_ids", []),
                }
        elif dst_key in _DOCTOR_AUTHORED_FIELDS:
            continue
        else:
            merged = _merge_text(defaults.get(dst_key), value)
            if merged:
                defaults[dst_key] = merged
                provenance[dst_key] = {
                    "source": "patient_confirmed_intake",
                    "source_kind": entry.get("source", "intake_extraction"),
                    "confirmed_by_patient": entry.get("confirmed_by_patient", True),
                    "evidence_message_ids": entry.get("evidence_message_ids", []),
                }

    # AI-derived summary is stored as labeled metadata, never in a
    # doctor-authored field.
    review = intake_session.patient_review_summary or {}
    if review.get("ai_generated_summary"):
        provenance["ai_generated_summary"] = {
            "source": "ai_generated",
            "source_kind": "intake_extraction",
            "confirmed_by_patient": False,
            "not_clinically_verified": True,
        }
        defaults["additional_notes"] = (
            "AI-assisted intake summary — not clinically verified.\n"
            + str(review["ai_generated_summary"])
        )
    defaults["provenance"] = provenance

    record, created = MedicalRecordDraft.objects.get_or_create(
        consultation=consultation,
        defaults=defaults,
    )

    if created:
        logger.info(
            "Created intake-derived draft %s for consultation %s",
            record.id, consultation.id,
        )
    return record