"""Canonical AI intake field registry and completion policy.

Single source of truth for:
- which fields exist;
- which are universal vs conditional;
- how each field is typed;
- deterministic completion rules.

DeepSeek may recommend that a conditional field is relevant.
The backend validates that recommendation against this registry.
"""

# ── Field types ──────────────────────────────────────────────────────────────
TEXT = "text"
LIST = "list"
BOOLEAN = "boolean"
INTEGER = "integer"


# ── Canonical registry ───────────────────────────────────────────────────────
# Every AI-extractable or patient-reportable field must appear here.
# Keys are the only values accepted in AI output, missing_fields, corrections,
# and collected metadata.
INTAKE_FIELDS: dict[str, dict] = {
    # ── Core complaint ────────────────────────────────────────────
    "chief_complaint": {
        "type": TEXT,
        "universal": True,
        "question": "What brings you in today?",
    },
    "symptoms": {
        "type": LIST,
        "universal": True,
        "question": "What symptoms are you experiencing?",
    },
    # ── Timing / progression ───────────────────────────────────────
    "onset": {
        "type": TEXT,
        "universal": True,
        "requires": "duration",
        "question": "When did this begin?",
        "pair_with": "duration",
    },
    "duration": {
        "type": TEXT,
        "universal": True,
        "requires": "onset",
        "question": "How long have you had these symptoms?",
    },
    "progression": {
        "type": TEXT,
        "universal": False,
        "conditional": True,
        "question": "Is it getting better, worse, or staying the same?",
    },
    # ── Severity / location / character ───────────────────────────
    "severity": {
        "type": TEXT,
        "universal": True,
        "question": "How severe is it, and how much does it affect your daily life?",
    },
    "location": {
        "type": TEXT,
        "universal": False,
        "conditional": True,
        "requires": "localized_symptom",
        "question": "Where on your body do you feel this?",
    },
    "character": {
        "type": TEXT,
        "universal": False,
        "question": "Can you describe the feeling — for example sharp, dull, burning, or pressure?",
    },
    # ── Aggravating / relieving ────────────────────────────────────
    "triggers": {
        "type": TEXT,
        "universal": False,
        "question": "Is there anything that makes it worse?",
    },
    "relieving_factors": {
        "type": TEXT,
        "universal": False,
        "question": "Is there anything that makes it better?",
    },
    "associated_symptoms": {
        "type": LIST,
        "universal": False,
        "question": "Are there any other symptoms that happen at the same time?",
    },
    # ── Recurrence ─────────────────────────────────────────────────
    "previous_episodes": {
        "type": TEXT,
        "universal": False,
        "conditional": True,
        "requires": "recurrence_relevant",
        "question": "Have you had this before?",
    },
    # ── History ────────────────────────────────────────────────────
    "past_medical_history": {
        "type": TEXT,
        "universal": True,
        "question": "Do you have any ongoing medical conditions?",
    },
    "surgical_history": {
        "type": TEXT,
        "universal": False,
        "question": "Have you had any surgeries?",
    },
    # ── Medications / allergies ────────────────────────────────────
    "current_medications": {
        "type": LIST,
        "universal": True,
        "question": "Are you currently taking any medications?",
    },
    "medication_changes": {
        "type": TEXT,
        "universal": False,
        "question": "Have you recently started, stopped, or changed any medication?",
    },
    "allergies": {
        "type": LIST,
        "universal": True,
        "question": "Do you have any allergies?",
    },
    "allergy_reactions": {
        "type": TEXT,
        "universal": False,
        "question": "What reaction do you get from that allergy?",
    },
    # ── Family / social / lifestyle ────────────────────────────────
    "family_history": {
        "type": TEXT,
        "universal": False,
        "conditional": True,
        "question": "Is there any relevant family medical history?",
    },
    "social_history": {
        "type": TEXT,
        "universal": False,
        "question": "Is there anything about your daily life or work that may be relevant?",
    },
    "substance_use": {
        "type": TEXT,
        "universal": False,
        "conditional": True,
        "question": "Do you smoke, drink alcohol, or use other substances?",
    },
    "pregnancy_possible": {
        "type": BOOLEAN,
        "universal": False,
        "conditional": True,
        "requires": "pregnancy_relevant",
        "question": "Could you be pregnant?",
    },
    "recent_travel_exposure": {
        "type": TEXT,
        "universal": False,
        "conditional": True,
        "question": "Have you recently travelled or been in contact with someone who is unwell?",
    },
    # ── Previous care / warnings / additional ──────────────────────
    "previous_tests_treatment": {
        "type": TEXT,
        "universal": False,
        "question": "Have you had any tests or treatment for this already?",
    },
    "warning_signs": {
        "type": TEXT,
        "universal": False,
        "question": "Is there anything that worries you most about this?",
    },
    "additional_concerns": {
        "type": TEXT,
        "universal": False,
        "question": "Is there anything else you would like to share?",
    },
}

# One of each pair required — onset XOR duration may be enough.
_TIMING_PAIR = {"onset", "duration"}

# Universal fields that must be answered (or explicitly declined/unknown
# only where policy allows) before review can be generated.
UNIVERSAL_REQUIRED = [
    name for name, spec in INTAKE_FIELDS.items()
    if spec.get("universal")
]

# Fields the patient may mark unknown without blocking review.
# Rationale: patient genuinely does not know is legitimate intake data.
UNKNOWN_ALLOWED_UNIVERSAL = {
    "current_medications",
    "allergies",
    "past_medical_history",
}

# Optional fields the patient may decline to answer without blocking review.
DECLINABLE_OPTIONAL = {
    "social_history",
    "substance_use",
    "family_history",
    "surgical_history",
    "previous_tests_treatment",
}

# Conditional relevance rules — allowlisted reasons the AI may propose.
CONDITIONAL_RELEVANCE_RULES = {
    "localized_symptom",
    "recurrence_relevant",
    "pregnancy_relevant",
    "family_history_relevant",
}

# Emergency screening is always required before any normal-flow persistence.
EMERGENCY_SCREEN_FIELD = "emergency_screen_completed"

# Patient confirmation of the review summary is always required.
CONFIRMATION_FIELD = "patient_confirmed"

VALID_FIELD_STATUSES = {
    "missing",
    "answered",
    "unknown",
    "declined",
    "not_applicable",
    "uncertain",
}

VALID_FIELD_SOURCES = {
    "patient_message",
    "patient_profile",
    "intake_extraction",
    "patient_correction",
}

VALID_CERTAINTY = {"explicit", "inferred", "uncertain"}


def require_pair_complete(answered: set[str]) -> bool:
    """Both onset and duration, or at least one, may satisfy timing requirement."""
    return bool(answered & _TIMING_PAIR) or bool(answered >= _TIMING_PAIR)


def field_is_universal(name: str) -> bool:
    return INTAKE_FIELDS.get(name, {}).get("universal", False)


def field_is_conditional(name: str) -> bool:
    return INTAKE_FIELDS.get(name, {}).get("conditional", False)


def field_question(name: str) -> str:
    return INTAKE_FIELDS.get(name, {}).get("question", "")