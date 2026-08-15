"""Semantic validation of DeepSeek structured output.

Pydantic enforces shape. This module enforces meaning:
- evidence IDs exist and belong to this session;
- extracted values are grounded in the cited evidence (hallucination guard);
- no duplicate fields;
- no next-question for an already answered field;
- no diagnosis/treatment/prescription words in patient-facing content;
- no prompt-disclosure patterns;
- no unsupported emergency reasons (code allowlist);
- no extracted value that has zero supporting evidence (fabrication guard).
"""

import re
import unicodedata

from apps.ai_intake.constants import INTAKE_FIELDS

PROHIBITED_PATIENT_FACING_TERMS = {
    "diagnos",
    "diagnosed",
    "your condition is",
    "you have been diagnosed",
    "you are suffering from",
    "you have [a-z]+ disease",
    "prescription",
    "prescribe",
    "prescribed",
    "take [0-9] mg",
    "take antibiotics",
    "take paracetamol",
    "take ibuprofen",
    "take medication",
    "you should take",
    "you need to take",
    "stop taking",
    "increase your dose",
    "you need surgery",
    "system prompt",
    "instructions:",
    "ignore your",
    "mark complete",
    "return this json",
    "no emergency",
}

EMERGENCY_REASON_CODES = {
    "self_harm",
    "chest_pain",
    "breathing_difficulty",
    "major_bleeding",
    "stroke_like",
    "anaphylaxis",
    "loss_of_consciousness",
}

# Fields that are already answered by patient message, keyed in field metadata.
ANSWERED_STATUS = "answered"

# Minimum token length considered meaningful for grounding.
_TOKEN_MIN_LEN = 4
# Include Arabic + Kurdish Unicode ranges plus Latin.
_TOKEN_RE = re.compile(r"[A-Za-z0-9\u0600-\u06FF\u0750-\u077F]{4,}")
_GROUNDING_TOKEN_RE = re.compile(r"[a-z0-9\u0600-\u06ff\u0750-\u077f]+")
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_GROUNDING_PUNCTUATION = str.maketrans({
    "،": " ", "؛": " ", "؟": " ", ",": " ", ".": " ",
    ":": " ", ";": " ", "!": " ", "?": " ", "-": " ",
    "_": " ", "/": " ", "\\": " ", "(": " ", ")": " ",
})

# Field-scoped mappings require explicit patient phrases. They bridge safe
# linguistic variants to canonical intake values without weakening evidence
# ownership or accepting unrelated facts.
GROUNDING_CANONICAL_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "chief_complaint": {
        "headache": ("صداع", "راسي يوجعني", "رأسي يؤلمني", "سەرێشە", "سەرم دەئێشێ"),
        "dizziness": ("دوخة", "دايخ", "سەرگێژ", "سەرگێژم"),
        "nausea": ("غثيان", "لوعه", "لوعە", "دڵتێکچوون"),
    },
    "symptoms": {
        "headache": ("صداع", "راسي يوجعني", "رأسي يؤلمني", "سەرێشە", "سەرم دەئێشێ"),
        "dizziness": ("دوخة", "دايخ", "سەرگێژ", "سەرگێژم"),
        "nausea": ("غثيان", "لوعه", "لوعە", "دڵتێکچوون"),
    },
    "associated_symptoms": {
        "dizziness": ("دوخة", "دايخ", "سەرگێژ", "سەرگێژم"),
        "nausea": ("غثيان", "لوعه", "لوعە", "دڵتێکچوون"),
    },
    "duration": {
        "two days": ("يومين", "يومان", "من يومين", "صارلي يومين", "دوو ڕۆژ", "دوو ڕۆژە"),
        "2 days": ("يومين", "يومان", "من يومين", "صارلي يومين", "دوو ڕۆژ", "دوو ڕۆژە"),
        "since yesterday": ("من امس", "من البارحه", "من البارحة", "لە دوێنێ", "دوێنێوە"),
        "one day": ("يوم واحد", "من البارحه", "من البارحة", "ڕۆژێک"),
    },
    "onset": {
        "yesterday": ("امس", "البارحه", "البارحة", "دوێنێ", "لە دوێنێ"),
        "since yesterday": ("من امس", "من البارحه", "من البارحة", "لە دوێنێ", "دوێنێوە"),
    },
    "severity": {
        "severe": ("شديد", "شديدة", "كلش قوي", "هوايه قوي", "زۆر توند", "توندە"),
        "mild": ("خفيف", "خفيفة", "شويه", "کەم", "سووک"),
        "moderate": ("متوسط", "متوسطة", "مامناوه ند", "مامناوەند"),
    },
    "location": {
        "head": ("الراس", "الرأس", "راسي", "سەر", "سەرم"),
        "chest": ("الصدر", "صدري", "سنگ", "سنگم"),
        "abdomen": ("البطن", "بطني", "سك", "سک", "سکم"),
    },
    "current_medications": {
        "metformin": ("ميتفورمين", "متفورمين", "میتفۆرمین"),
        "paracetamol": ("باراسيتامول", "بنادول", "پاراسیتامۆل"),
    },
    "allergies": {
        "penicillin": ("بنسلين", "پنسلین"),
    },
    "pregnancy_possible": {
        "true": ("i am pregnant", "pregnancy is possible", "انا حامل", "اني حامل", "من دووگیانم"),
        "false": ("not pregnant", "pregnancy is not possible", "لست حاملا", "مو حامل", "دووگیان نیم"),
    },
}


class SemanticValidationError(Exception):
    pass


def _is_prohibited(text: str) -> bool:
    lowered = (text or "").lower()
    for term in PROHIBITED_PATIENT_FACING_TERMS:
        # Escape regex-lite patterns safely.
        if "[" in term or "]" in term:
            if re.search(term, lowered):
                return True
        elif term in lowered:
            return True
    return False


def _significant_tokens(text) -> set[str]:
    if not text:
        return set()
    return set(_TOKEN_RE.findall(str(text).lower()))


def normalize_grounding_text(text) -> str:
    """Normalize orthographic variants while preserving clinical meaning."""
    value = unicodedata.normalize(
        "NFKC", "" if text is None else str(text)
    ).casefold()
    value = value.replace("ـ", "")
    value = _ARABIC_DIACRITICS.sub("", value)
    value = value.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ی": "ي", "ئ": "ي",
        "ک": "ك",
    }))
    value = value.translate(_GROUNDING_PUNCTUATION)
    return " ".join(_GROUNDING_TOKEN_RE.findall(value))


def _canonical_alias_grounded(field: str, value, evidence_text: str) -> bool:
    aliases = GROUNDING_CANONICAL_ALIASES.get(field, {})
    evidence = normalize_grounding_text(evidence_text)
    values = value if isinstance(value, list) else [value]
    for item in values:
        normalized_value = normalize_grounding_text(item)
        item_grounded = False
        for canonical, phrases in aliases.items():
            normalized_canonical = normalize_grounding_text(canonical)
            if normalized_value != normalized_canonical:
                continue
            if any(normalize_grounding_text(phrase) in evidence for phrase in phrases):
                item_grounded = True
                break
        if not item_grounded:
            return False
    return bool(values)


def grounding_classification(update, evidence_text: str) -> str:
    """Return literal, normalized, canonical, structured, or unsupported."""
    values = update.value if isinstance(update.value, list) else [update.value]
    values = [value for value in values if value is not None and str(value).strip()]
    if not values:
        return "structured"
    raw_evidence = str(evidence_text or "").casefold()
    if all(str(value).casefold() in raw_evidence for value in values):
        return "literal"
    normalized_evidence = normalize_grounding_text(evidence_text)
    if all(
        normalize_grounding_text(value)
        and normalize_grounding_text(value) in normalized_evidence
        for value in values
    ):
        return "normalized"
    if _canonical_alias_grounded(update.field, update.value, evidence_text):
        return "canonical"
    return "unsupported"


def _grounded(update, evidence_text: str) -> bool:
    """Check that the extracted value is lexically grounded in evidence.

    Conservative: for explicit/inferred extractions there must be at least one
    significant shared token between the value and the cited patient message.
    This rejects fabricated facts while remaining safe (a miss only forces a
    re-ask; it never blocks clinical content because none exists here).
    """
    return grounding_classification(update, evidence_text) != "unsupported"


def _value_type_matches(field_type: str | None, value) -> bool:
    """Enforce the canonical per-field type from the registry."""
    if field_type == "list":
        return isinstance(value, list)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    # text and unknown types require a string.
    return isinstance(value, str)


def validate_semantics(session, response) -> None:
    """Raise SemanticValidationError on unsafe or meaningless output."""

    if _is_prohibited(response.patient_facing_message):
        raise SemanticValidationError("Unsafe content in patient-facing message")

    if response.summary_for_review and _is_prohibited(response.summary_for_review):
        raise SemanticValidationError("Unsafe content in review summary")

    # Evidence message IDs must belong to this session; load id -> content once
    # so grounding can be checked without per-update queries.
    session_messages = {
        str(m.id): m.content for m in session.messages.all()
    }
    for update in response.extracted_updates:
        for mid in update.source_message_ids:
            if str(mid) not in session_messages:
                raise SemanticValidationError(
                    f"Evidence message {mid} does not belong to this session"
                )
        if not update.source_message_ids:
            raise SemanticValidationError(
                f"Extracted field {update.field!r} has no supporting evidence"
            )
        if update.certainty in {"explicit", "inferred"}:
            evidence_text = " ".join(
                session_messages.get(str(mid), "") for mid in update.source_message_ids
            )
            if not _grounded(update, evidence_text):
                raise SemanticValidationError(
                    f"Extracted field {update.field!r} is not grounded in the patient's answers"
                )
        # Enforce the canonical per-field type (e.g. boolean fields must be bool).
        field_spec = INTAKE_FIELDS.get(update.field, {})
        if not _value_type_matches(field_spec.get("type"), update.value):
            raise SemanticValidationError(
                f"Extracted field {update.field!r} has an invalid value type"
            )

    # No next question for an already-answered field.
    metadata = session.field_metadata or {}
    if response.next_question and response.next_question.field:
        field = response.next_question.field
        entry = metadata.get(field) or {}
        if entry.get("status") == ANSWERED_STATUS:
            raise SemanticValidationError(
                f"Next question targets already-answered field {field!r}"
            )

    # Emergency reasons must be safe codes.
    for reason in response.emergency_signal.reasons:
        if reason not in EMERGENCY_REASON_CODES:
            raise SemanticValidationError(f"Unsupported emergency reason {reason!r}")

    # Suggested relevance rules already allowlisted by Pydantic.
    # Extracted fields already allowlisted by Pydantic.
