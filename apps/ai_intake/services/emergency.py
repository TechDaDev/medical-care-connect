"""
Deterministic keyword-based emergency screening.

Run BEFORE any AI call or normal-flow persistence.  If this flags an
emergency, the conversation enters escalated mode without an AI round-trip.

Limitations (documented):
- keyword matcher, not a clinical rule engine; no reliability claim;
- tight negation/family-history windows reduce obvious false positives but
  cannot guarantee accuracy;
- clinician-reviewed rule sets should replace/augment this matcher when
  they become available.
"""

# ── Tier 1: Immediate red flags ──────────────────────────────────────────────

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
    "can't catch my breath",
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
    "loss of consciousness",
]

_ALLERGY_KEYWORDS = [
    "anaphylaxis",
    "severe allergic reaction",
    "throat swelling",
    "tongue swelling",
    "airway closing",
]

# ── Tier 2: Localized variants ───────────────────────────────────────────────
# Codes allowlisted by semantic_validation.EMERGENCY_REASON_CODES.

_ARABIC_EMERGENCY = [
    ("ألم في الصدر", "chest_pain", "emergency"),
    ("ألم صدر", "chest_pain", "emergency"),
    ("ضيق التنفس", "breathing_difficulty", "urgent"),
    ("لا أستطيع التنفس", "breathing_difficulty", "emergency"),
    ("نزيف شديد", "major_bleeding", "emergency"),
    ("انتحار", "self_harm", "emergency"),
    ("أريد أن أقتل نفسي", "self_harm", "emergency"),
    ("سكتة", "stroke_like", "emergency"),
    ("تخدير مفاجئ", "stroke_like", "emergency"),
    ("صعوبة في الكلام", "stroke_like", "emergency"),
    ("فقدان الوعي", "loss_of_consciousness", "emergency"),
]

_KURDISH_EMERGENCY = [
    ("ئازاری سینە", "chest_pain", "emergency"),
    ("نەتوانم هەناسە بدەم", "breathing_difficulty", "emergency"),
    ("تەنگی هەناسە", "breathing_difficulty", "urgent"),
    ("لێدانەوەی دڵ", "chest_pain", "emergency"),
    ("خوێنێکی زۆر", "major_bleeding", "emergency"),
    ("هەوڵی خۆکوشتن", "self_harm", "emergency"),
    ("دەمەوێ خۆم بکوژم", "self_harm", "emergency"),
    ("بێهۆشی", "loss_of_consciousness", "emergency"),
]

_NEGATION_TOKENS = [
    "no ",
    "not ",
    "never ",
    "don't ",
    "dont ",
    "doesn't ",
    "didn't ",
    "wasn't ",
    "without ",
    "no history of ",
    "no sign of ",
    "not a sign of ",
]

_FAMILY_HISTORY_TOKENS = [
    "my father",
    "my mother",
    "my brother",
    "my sister",
    "my uncle",
    "my aunt",
    "my grandfather",
    "my grandmother",
    "my husband",
    "my wife",
    "my friend",
    "my cousin",
    "my son",
    "my daughter",
]

# Self-harm keywords are NEVER suppressed by family history or distant
# past-tense context — a safety signal about anyone still warrants review.
_UNSUPPRESSABLE = set(_SUICIDE_KEYWORDS)


def _window_negated(text: str, keyword: str, window: int = 30) -> bool:
    idx = text.find(keyword)
    if idx < 0:
        return False
    start = max(0, idx - window)
    before = text[start:idx]
    for token in _NEGATION_TOKENS:
        if token in before:
            return True
    return False


def _window_family_history(text: str, keyword: str, window: int = 40) -> bool:
    idx = text.find(keyword)
    if idx < 0:
        return False
    start = max(0, idx - window)
    before = text[start:idx]
    for token in _FAMILY_HISTORY_TOKENS:
        if token in before:
            return True
    return False


def screen_patient_input(text: str) -> dict:
    """Check patient text for emergency keywords.

    Returns:
        dict with keys:
          - detected (bool)
          - level (str): "emergency", "urgent", "warning", "none"
          - reasons (list[str] of safe codes)
    """
    text = (text or "").strip()
    if not text:
        return {"detected": False, "level": "none", "reasons": []}

    lowered = text.lower()

    # Localized matchers run first; Arabic/Kurdish negation is much harder to
    # window reliably, so we stay conservative and escalate any match.
    for phrase, code, level in _ARABIC_EMERGENCY:
        if phrase in text:
            return {"detected": True, "level": level, "reasons": [code]}
    for phrase, code, level in _KURDISH_EMERGENCY:
        if phrase in text:
            return {"detected": True, "level": level, "reasons": [code]}

    for kw in _SUICIDE_KEYWORDS:
        if kw in lowered:
            # Never suppress self-harm by negation or family history.
            return {"detected": True, "level": "emergency", "reasons": ["self_harm"]}

    # Non-self-harm keywords: suppress only when the keyword is tightly
    # negated in the same clause, or clearly belongs to family history.
    for kw in _CHEST_PAIN_KEYWORDS:
        if kw in lowered and not _window_negated(lowered, kw) and not _window_family_history(lowered, kw):
            return {"detected": True, "level": "emergency", "reasons": ["chest_pain"]}
    for kw in _STROKE_KEYWORDS:
        if kw in lowered and not _window_negated(lowered, kw) and not _window_family_history(lowered, kw):
            return {"detected": True, "level": "emergency", "reasons": ["stroke_like"]}
    for kw in _BREATHING_KEYWORDS:
        if kw in lowered and not _window_negated(lowered, kw):
            return {"detected": True, "level": "urgent", "reasons": ["breathing_difficulty"]}
    for kw in _BLEEDING_KEYWORDS:
        if kw in lowered and not _window_negated(lowered, kw):
            return {"detected": True, "level": "urgent", "reasons": ["major_bleeding"]}
    for kw in _ALLERGY_KEYWORDS:
        if kw in lowered and not _window_negated(lowered, kw):
            return {"detected": True, "level": "urgent", "reasons": ["anaphylaxis"]}

    return {"detected": False, "level": "none", "reasons": []}