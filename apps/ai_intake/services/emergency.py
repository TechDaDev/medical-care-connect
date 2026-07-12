"""
Deterministic keyword-based emergency screening.

Run BEFORE any AI call. If this flags an emergency, the conversation
starts in escalated mode without spending an AI round-trip.
"""

# ── Tier 1: Immediate red flags ──────────────────────────────────────
# These patterns indicate a life-threatening situation that should skip
# the normal intake flow entirely.

_SUICIDE_KEYWORDS = [
    "suicide",
    "kill myself",
    "end my life",
    "want to die",
    "hurt myself",
    "self-harm",
    "self harm",
    "suicidal",
]

_CHEST_PAIN_KEYWORDS = [
    "crushing chest pain",
    "severe chest pain",
    "chest tightness",
    "heart attack",
    "cardiac arrest",
]

_BREATHING_KEYWORDS = [
    "can't breathe",
    "cannot breathe",
    "difficulty breathing",
    "severe shortness of breath",
    "choking",
    "not breathing",
    "stopped breathing",
]

_BLEEDING_KEYWORDS = [
    "severe bleeding",
    "uncontrolled bleeding",
    "massive blood loss",
    "profuse bleeding",
    "gushing blood",
]

_STROKE_KEYWORDS = [
    "stroke symptom",
    "facial droop",
    "arm weakness",
    "slurred speech",
    "sudden numbness",
    "sudden paralysis",
    "cannot speak",
]

_ALLERGY_KEYWORDS = [
    "anaphylaxis",
    "severe allergic reaction",
    "throat swelling",
    "tongue swelling",
    "airway closing",
]


def screen_patient_input(text: str) -> dict:
    """Check patient text for emergency keywords.

    Returns:
        dict with keys:
          - detected (bool)
          - level (str): "emergency", "urgent", "warning", "none"
          - reasons (list[str])
    """
    lowered = text.lower()

    for kw in _SUICIDE_KEYWORDS:
        if kw in lowered:
            return {
                "detected": True,
                "level": "emergency",
                "reasons": [f"Self-harm indicator detected: '{kw}'"],
            }

    for kw in _CHEST_PAIN_KEYWORDS:
        if kw in lowered:
            return {
                "detected": True,
                "level": "emergency",
                "reasons": [f"Cardiac indicator detected: '{kw}'"],
            }

    for kw in _BREATHING_KEYWORDS:
        if kw in lowered:
            return {
                "detected": True,
                "level": "urgent",
                "reasons": [f"Respiratory indicator detected: '{kw}'"],
            }

    for kw in _BLEEDING_KEYWORDS:
        if kw in lowered:
            return {
                "detected": True,
                "level": "urgent",
                "reasons": [f"Bleeding indicator detected: '{kw}'"],
            }

    for kw in _STROKE_KEYWORDS:
        if kw in lowered:
            return {
                "detected": True,
                "level": "emergency",
                "reasons": [f"Stroke indicator detected: '{kw}'"],
            }

    for kw in _ALLERGY_KEYWORDS:
        if kw in lowered:
            return {
                "detected": True,
                "level": "urgent",
                "reasons": [f"Allergic indicator detected: '{kw}'"],
            }

    return {"detected": False, "level": "none", "reasons": []}
