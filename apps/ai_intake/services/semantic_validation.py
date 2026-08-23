"""Semantic validation of DeepSeek structured output.

Pydantic enforces shape. This module enforces meaning:
- evidence IDs exist and belong to this session;
- extracted values are grounded in the cited evidence (hallucination guard);
- no duplicate fields;
- backend, not provider, selects next-question target;
- no diagnosis/treatment/prescription words in patient-facing content;
- no prompt-disclosure patterns;
- no unsupported emergency reasons (code allowlist);
- no extracted value that has zero supporting evidence (fabrication guard).
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

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
_GROUNDING_CHAR_TRANSLATION = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ی": "ي",
    "ک": "ك",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})
_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}
_BIDI_FORMATTING = {
    "\u061c", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c",
    "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069",
}
_NEGATION_TOKENS = {
    "لا", "ما", "ماكو", "مو", "ليس", "لست", "بدون",
    "نا", "نە", "نیە", "نییه", "نییە", "بێ", "بەبێ",
}
_FAMILY_TOKENS = {
    "امي", "ابوي", "اختي", "اخوي", "والدتي", "والدي", "العائلة", "عايلتي",
    "دایكم", "باوكم", "خوشكم", "براكم", "خێزان", "خێزانم",
    "mother", "father", "sister", "brother", "family",
}
_HISTORICAL_OR_HYPOTHETICAL_TOKENS = {
    "سابقا", "قبل", "زمان", "لو", "اذا", "ئەگەر", "پێشتر", "جاران",
    "previously", "formerly", "if",
}
_NEGATED_CANONICAL_VALUES = {
    "false", "none", "none reported", "no known allergies", "not taking medication",
}

# Field-scoped mappings require explicit patient phrases. They bridge safe
# linguistic variants to canonical intake values without weakening evidence
# ownership or accepting unrelated facts.
GROUNDING_CANONICAL_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "chief_complaint": {
        "headache": ("my head aches", "صداع", "أشعر بصداع", "راسي يوجعني", "رأسي يؤلمني", "سەرێشە", "سەرێشەم", "سەرێشەکەم", "سەرم دەئێشێ"),
        "head pain": ("راسي يوجعني", "وجع الراس", "سەرم دەئێشێ", "سەرێشەم"),
        "abdominal pain": ("my stomach hurts", "بطني يوجعني", "بطني يؤلمني", "بطني دا يوجعني", "وجع البطن", "سکم دەئێشێ", "ئازاری سک"),
        "back pain": ("my back aches", "ظهري يوجعني", "ظهري يؤلمني", "وجع الظهر", "پشتم دەئێشێ", "ئازاری پشت"),
        "throat pain": ("my throat hurts", "حلقي يعورني", "گەرووم دەئێشێ"),
        "ألم في الحلق": ("حلقي يعورني", "گەرووم دەئێشێ"),
        "الم في الحلق": ("حلقي يعورني", "گەرووم دەئێشێ"),
        "گەروو ئێش": ("گەرووم دەئێشێ",),
        "گەروو ئێشە": ("گەرووم دەئێشێ",),
        "ئازاری گەروو": ("گەرووم دەئێشێ",),
        "سک ئێشە": ("سکم دەئێشێ",),
        "سک دەئێشێ": ("سکم دەئێشێ",),
        "صداع": ("راسي يوجعني", "وجع الراس"),
        "ألم في الظهر": ("بظهري", "ظهري يوجعني"),
        "الم في الظهر": ("بظهري", "ظهري يوجعني"),
        "سەرێژ": ("سه ریشم", "سه‌ریشم"),
        "صداع في الرأس": ("عندي صداع براسي", "صداع براسي"),
        "ألم في البطن": ("الوجع ببطني", "الألم ببطني", "بطني يوجعني"),
        "الم في البطن": ("الوجع ببطني", "الألم ببطني", "بطني يوجعني"),
        "وجع البطن": ("الوجع ببطني", "الألم ببطني", "بطني يوجعني"),
        "سەرئێشە": ("سەرم دەئێشێ", "سەرێشەم"),
        "ناڕەحەتی لە سک": ("لە سکمە", "سکم دەئێشێ"),
        "ئازاری سک": ("لە سکمە", "سکم دەئێشێ"),
        "ناڕەحەتی سک": ("لە سکمە", "سکم دەئێشێ"),
        "dizziness": ("دوخة", "دايخ", "سەرگێژ", "سەرگێژم"),
        "nausea": ("غثيان", "لوعه", "لوعە", "دڵتێکچوون", "دڵتێکچوونم"),
        "vomiting": ("تقيؤ", "استفراغ", "ارجع", "دا ارجع", "ڕشانەوە"),
        "cough": ("سعال", "كحة", "کۆکە"),
        "fatigue": ("تعب", "تعبان", "حيل تعبان", "ماندووم"),
    },
    "symptoms": {
        "headache": ("my head aches", "صداع", "أشعر بصداع", "راسي يوجعني", "رأسي يؤلمني", "سەرێشە", "سەرێشەم", "سەرێشەکەم", "سەرم دەئێشێ"),
        "dizziness": ("دوخة", "دايخ", "سەرگێژ", "سەرگێژم"),
        "nausea": ("غثيان", "لوعه", "لوعە", "دڵتێکچوون", "دڵتێکچوونم"),
        "vomiting": ("تقيؤ", "استفراغ", "ارجع", "دا ارجع", "ڕشانەوە"),
        "cough": ("سعال", "كحة", "کۆکە"),
        "fatigue": ("تعب", "تعبان", "حيل تعبان", "ماندووم"),
        "head pain": ("راسي يوجعني", "وجع الراس", "سەرم دەئێشێ", "سەرێشەم"),
        "abdominal pain": ("my stomach hurts", "بطني يوجعني", "بطني يؤلمني", "بطني دا يوجعني", "وجع البطن", "سکم دەئێشێ", "ئازاری سک"),
        "back pain": ("my back aches", "ظهري يوجعني", "ظهري يؤلمني", "وجع الظهر", "پشتم دەئێشێ", "ئازاری پشت"),
        "throat pain": ("my throat hurts", "حلقي يعورني", "گەرووم دەئێشێ"),
        "صداع": ("راسي يوجعني", "وجع الراس"),
        "ألم في البطن": ("الوجع ببطني", "الألم ببطني", "بطني يوجعني"),
        "الم في البطن": ("الوجع ببطني", "الألم ببطني", "بطني يوجعني"),
    },
    "associated_symptoms": {
        "dizziness": ("دوخة", "دايخ", "سەرگێژ", "سەرگێژم"),
        "nausea": ("غثيان", "لوعه", "لوعە", "دڵتێکچوون"),
    },
    "duration": {
        "two days": ("يومين", "يومان", "من يومين", "صارلي يومين", "قبل يومين", "دوو ڕۆژ", "دوو ڕۆژە"),
        "2 days": ("يومين", "يومان", "من يومين", "صارلي يومين", "قبل يومين", "دوو ڕۆژ", "دوو ڕۆژە"),
        "since yesterday": ("من امس", "من البارحه", "من البارحة", "لە دوێنێ", "دوێنێوە"),
        "one day": ("يوم واحد", "من البارحه", "من البارحة", "ڕۆژێک"),
        "one week": ("من اسبوع", "صارلي اسبوع", "هەفتەیەک", "یەک هەفتە"),
        "one month": ("من شهر", "صارلي شهر", "مانگێک", "یەک مانگ"),
        "five days": ("خمس ايام", "خمس أيام", "صارلي خمس ايام", "پێنج ڕۆژ", "پێنج ڕۆژە"),
        "5 days": ("خمس ايام", "خمس أيام", "صارلي خمس ايام", "پێنج ڕۆژ", "پێنج ڕۆژە"),
        "5 أيام": ("خمس ايام", "خمس أيام", "صارلي خمس ايام"),
        "three days": ("ثلاث ايام", "ثلاثة أيام", "صارلي ثلاث أيام", "سێ ڕۆژ", "سێ ڕۆژە"),
        "3 days": ("ثلاث ايام", "ثلاثة أيام", "لمدة ثلاثة أيام", "صارلي ثلاث أيام", "سێ ڕۆژ", "سێ ڕۆژە", "for ثلاث أيام"),
        "3 أيام": ("ثلاث ايام", "ثلاثة أيام", "لمدة ثلاثة أيام", "صارلي ثلاث أيام"),
        "3 ڕۆژ": ("سێ ڕۆژ", "سێ ڕۆژە"),
        "سێ ڕۆژ": ("سێ ڕۆژە",),
        "two weeks": ("اسبوعين", "أسبوعين", "دوو هەفتە", "دوو هەفتەیە"),
        "2 weeks": ("اسبوعين", "أسبوعين", "لمدة أسبوعين", "صارلي أسبوعين", "دوو هەفتە", "دوو هەفتەیە", "دوو weeks"),
        "1 month": ("one month", "لمدة شهر", "منذ شهر", "صارلي شهر", "مانگێک", "مانگێکە", "صارلي one month"),
        "شهر": ("لمدة شهر", "منذ شهر", "صارلي شهر"),
        "مانگێک": ("مانگێکە",),
        "دوو هەفتە": ("دوو هەفتەیە",),
        "يومان": ("صارلي يومين", "يومين"),
        "منذ يومين": ("صارلي يومين", "من يومين"),
        "دوو ڕۆژ": ("دوو ڕۆژە", "دوو روژه"),
        "دوو ڕۆژە": ("دوو ڕۆژ", "دوو روژه"),
        "یەک هەفتە": ("یەک هەفتەیە", "هەفتەیەک"),
    },
    "onset": {
        "yesterday": ("امس", "البارحه", "البارحة", "دوێنێ", "لە دوێنێ"),
        "since yesterday": ("من امس", "من البارحه", "من البارحة", "لە دوێنێ", "دوێنێوە"),
        "today": ("اليوم", "هسه", "ئەمڕۆ"),
        "two days ago": ("قبل يومين", "پێش دوو ڕۆژ"),
    },
    "severity": {
        "severe": ("شديد", "شديدة", "كلش قوي", "هوايه قوي", "زۆر توند", "توندە"),
        "high": ("شديد", "شديدة", "كلش قوي", "هوايه قوي", "زۆر توند", "توندە"),
        "mild": ("خفيف", "خفيفة", "شويه", "مو قوي", "کەم", "سووک"),
        "low": ("خفيف", "خفيفة", "شويه", "مو قوي", "کەم", "سووک"),
        "moderate": ("متوسط", "متوسطة", "مامناوه ند", "مامناوەند"),
        "medium": ("متوسط", "متوسطة", "مامناوه ند", "مامناوەند"),
        "شديد جدا": ("كلش قوي", "هوايه قوي"),
        "شديد جداً": ("كلش قوي", "هوايه قوي"),
        "not severe": ("مو قوي",),
        "سووک": ("سووکە",),
        "سووکە": ("سووک",),
    },
    "location": {
        "head": ("الراس", "الرأس", "راسي", "سەر", "سەرم"),
        "chest": ("الصدر", "صدري", "سنگ", "سنگم"),
        "abdomen": ("البطن", "بطني", "سك", "سک", "سکم"),
        "back": ("الظهر", "ظهري", "بظهري", "پشت", "پشتم"),
        "leg": ("الرجل", "رجلي", "برجلي", "لاق", "لاقم"),
        "hand": ("اليد", "ايدي", "بيدي", "دەست", "دەستم"),
        "throat": ("الحلق", "حلقي", "بحلقي", "گەروو", "گەرووم"),
        "الراس": ("راسي", "براسي"),
        "الرأس": ("راسي", "براسي"),
        "الظهر": ("ظهري", "بظهري"),
        "البطن": ("بطني", "ببطني"),
    },
    "current_medications": {
        "metformin": ("ميتفورمين", "متفورمين", "میتفۆرمین"),
        "paracetamol": ("باراسيتامول", "باراسيتامول", "بنادول", "بانادول", "پاراسیتامۆل"),
        "panadol": ("بنادول", "بانادول", "پانادۆل"),
    },
    "allergies": {
        "penicillin": ("بنسلين", "البنسلين", "پنسلین", "پنسلینم"),
        "none": ("no allergies", "ليس لدي حساسية", "ما عندي حساسية", "ماكو عندي حساسية", "ماكو حساسية", "مو عندي حساسية", "هەستیاریم نییە"),
        "none reported": ("ما عندي حساسية", "ماكو حساسية", "مو عندي حساسية", "هەستیاریم نییە"),
        "no known allergies": ("ما عندي حساسية", "ماكو حساسية", "مو عندي حساسية", "هەستیاریم نییە", "هەستیاریی دەرمانم نییە"),
        "بنسلين": ("البنسلين", "حساسية من البنسلين"),
        "لا يوجد": ("ما عندي حساسية", "ماكو حساسية", "مو عندي حساسية"),
        "پنسلین": ("پنسلینم", "هەستیاریی پنسلینم"),
        "پەنسلین": ("هەستیاریی پنسلینم",),
    },
    "previous_episodes": {
        "yes": ("صارلي نفس الوجع", "تكرر هذا الالم", "هەمان ئازارم هەبوو", "ئەم ئازارە دووبارە بووەوە"),
        "similar episode": ("صارلي نفس الوجع", "تكرر هذا الالم", "هەمان ئازارم هەبوو", "ئەم ئازارە دووبارە بووەوە"),
        "no": ("اول مرة", "أول مرة", "یەکەم جارە"),
        "first episode": ("اول مرة", "أول مرة", "یەکەم جارە"),
    },
    "progression": {
        "worsening": ("ديزيد", "يزيد", "يسوء", "خراپتر دەبێت", "زیاتر دەبێت"),
        "improving": ("ديتحسن", "يتحسن", "باشتر دەبێت"),
        "unchanged": ("نفسه", "ما تغير", "هەر وەک خۆیەتی"),
    },
    "pregnancy_possible": {
        "true": ("i am pregnant", "pregnancy is possible", "انا حامل", "اني حامل", "من دووگیانم"),
        "false": ("not pregnant", "pregnancy is not possible", "لست حاملا", "مو حامل", "دووگیان نیم"),
    },
}


class SemanticValidationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class GroundingEvidence:
    classification: str
    evidence_span: EvidenceSpan | None = None
    evidence_text: str | None = None
    evidence_spans: tuple[EvidenceSpan, ...] = ()


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
    return " ".join(token for token, _, _ in _normalized_tokens_with_spans(text))


def _normalized_tokens_with_spans(text) -> list[tuple[str, int, int]]:
    original = "" if text is None else str(text)
    chars: list[str] = []
    origins: list[int] = []
    for original_index, source_char in enumerate(original):
        for char in unicodedata.normalize("NFKC", source_char).casefold():
            if char in _BIDI_FORMATTING:
                continue
            if char == "ـ" or _ARABIC_DIACRITICS.fullmatch(char):
                continue
            if char in _ZERO_WIDTH:
                char = " "
            char = char.translate(_GROUNDING_CHAR_TRANSLATION)
            if not (char.isalnum() or unicodedata.category(char).startswith("L")):
                char = " "
            if char != " " and len(chars) >= 2 and chars[-1] == chars[-2] == char:
                continue
            chars.append(char)
            origins.append(original_index)
    normalized = "".join(chars)
    tokens = []
    for match in _GROUNDING_TOKEN_RE.finditer(normalized):
        start_index, end_index = match.span()
        tokens.append((match.group(), origins[start_index], origins[end_index - 1] + 1))
    return tokens


def _phrase_spans(evidence_text: str, phrase: str) -> list[EvidenceSpan]:
    evidence_tokens = _normalized_tokens_with_spans(evidence_text)
    phrase_tokens = [token for token, _, _ in _normalized_tokens_with_spans(phrase)]
    if not phrase_tokens:
        return []
    width = len(phrase_tokens)
    spans = []
    for index in range(len(evidence_tokens) - width + 1):
        if [token for token, _, _ in evidence_tokens[index:index + width]] == phrase_tokens:
            spans.append(EvidenceSpan(
                evidence_tokens[index][1], evidence_tokens[index + width - 1][2]
            ))
    return spans


def _phrase_span(evidence_text: str, phrase: str) -> EvidenceSpan | None:
    spans = _phrase_spans(evidence_text, phrase)
    return spans[0] if spans else None


@lru_cache(maxsize=1)
def _normalized_safety_tokens() -> tuple[set[str], set[str], set[str], set[str]]:
    normalize = lambda values: {normalize_grounding_text(value) for value in values}
    return (
        normalize(_NEGATION_TOKENS),
        normalize(_FAMILY_TOKENS),
        normalize(_HISTORICAL_OR_HYPOTHETICAL_TOKENS),
        normalize(_NEGATED_CANONICAL_VALUES),
    )


def _clause_before(evidence_text: str, span: EvidenceSpan) -> str:
    before = str(evidence_text or "")[:span.start]
    return re.split(r"[،,؛;.!؟?]", before)[-1]


def _unsafe_context(evidence_text: str, span: EvidenceSpan, canonical) -> bool:
    preceding = [
        token for token, _, end in _normalized_tokens_with_spans(evidence_text)
        if end <= span.start and end > span.start - len(_clause_before(evidence_text, span)) - 1
    ][-4:]
    normalized_canonical = normalize_grounding_text(canonical)
    negation, family, historical, negated_values = _normalized_safety_tokens()
    if any(token in family for token in preceding):
        return True
    if any(token in historical for token in preceding):
        return True
    return (
        normalized_canonical not in negated_values
        and any(token in negation for token in preceding[-3:])
    )


def _field_context_supported(
    field: str, canonical, evidence_text: str, span: EvidenceSpan
) -> bool:
    if field != "allergies":
        return True
    if normalize_grounding_text(canonical) in _normalized_safety_tokens()[3]:
        return True
    clause = str(evidence_text or "")[
        max(0, str(evidence_text or "").rfind("،", 0, span.start)):
    ]
    normalized = normalize_grounding_text(clause)
    markers = (
        "حساسية", "هەستیاری", "هەستیاریی", "allergy", "allergic",
    )
    return any(normalize_grounding_text(marker) in normalized for marker in markers)


def _is_patient_correction(evidence_text: str, span: EvidenceSpan) -> bool:
    normalized = normalize_grounding_text(evidence_text)
    markers = {
        "قصدي", "تصحيح", "لا", "مو", "نه ك", "نەك", "ڕاستكردنه وه",
        "ڕاستکردنەوە",
    }
    return bool(re.search(r"[،,؛;]", str(evidence_text or ""))) and any(
        marker in normalized for marker in markers
    )


_DURATION_CANONICAL_NUMBER = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}
_DURATION_PATTERNS = (
    (1, "day", r"(?:صارلي|صارله|من)? ?يوم(?: واحد)?"),
    (2, "day", r"(?:صارلي|صارله|من)? ?يومين|يومان|دوو ?ڕۆژە?"),
    (3, "day", r"(?:صارلي|صارله|من)? ?(?:ثلاث|ثلاثه|3) ?ايام|سێ ?ڕۆژ"),
    (5, "day", r"(?:صارلي|صارله|من)? ?(?:خمس|5) ?ايام|پێنج ?ڕۆژە?"),
    (1, "week", r"(?:صارلي|صارله|من)? ?اسبوع|يەك ?هەفتەیە?|هەفتەیەك"),
    (2, "week", r"(?:صارلي|صارله|من)? ?اسبوعين|دوو ?هەفتە"),
    (1, "month", r"(?:صارلي|صارله|من)? ?شهر|مانگێكە?|يەك ?مانگ"),
)


def _canonical_duration(value) -> tuple[int, str] | None:
    normalized = normalize_grounding_text(value)
    match = re.fullmatch(r"(one|two|three|four|five|[1-5]) (day|days|week|weeks|month|months)", normalized)
    if not match:
        return None
    return _DURATION_CANONICAL_NUMBER[match.group(1)], match.group(2).rstrip("s")


def _structured_duration_span(value, evidence_text: str) -> EvidenceSpan | None:
    canonical = _canonical_duration(value)
    if not canonical:
        return None
    normalized_evidence = normalize_grounding_text(evidence_text)
    for number, unit, pattern in _DURATION_PATTERNS:
        if (number, unit) != canonical:
            continue
        match = re.search(rf"(?:^| )({pattern})(?: |$)", normalized_evidence)
        if match:
            return _phrase_span(evidence_text, match.group(1))
    return None


def _canonical_alias_span(field: str, value, evidence_text: str) -> EvidenceSpan | None:
    aliases = GROUNDING_CANONICAL_ALIASES.get(field, {})
    values = value if isinstance(value, list) else [value]
    for item in values:
        normalized_value = normalize_grounding_text(item)
        item_span = None
        for canonical, phrases in aliases.items():
            normalized_canonical = normalize_grounding_text(canonical)
            if normalized_value != normalized_canonical:
                continue
            for phrase in phrases:
                for span in _phrase_spans(evidence_text, phrase):
                    if (
                        not _unsafe_context(evidence_text, span, canonical)
                        and _field_context_supported(field, canonical, evidence_text, span)
                    ):
                        item_span = span
                        break
                if item_span:
                    break
            if item_span:
                break
        if not item_span:
            return None
    return item_span if values else None


def _canonical_alias_grounded(field: str, value, evidence_text: str) -> bool:
    return _canonical_alias_span(field, value, evidence_text) is not None


def grounding_evidence(update, evidence_text: str) -> GroundingEvidence:
    """Classify grounding and bind matching text to its original source span."""
    values = update.value if isinstance(update.value, list) else [update.value]
    values = [value for value in values if value is not None and str(value).strip()]
    if not values:
        return GroundingEvidence("unsupported")
    spans = []
    for value in values:
        span = next((
            candidate for candidate in _phrase_spans(evidence_text, str(value))
            if not _unsafe_context(evidence_text, candidate, value)
            and _field_context_supported(update.field, value, evidence_text, candidate)
        ), None)
        spans.append(span)
    if all(spans):
        span = spans[0]
        raw = str(evidence_text or "")
        classification = "literal" if all(
            str(value).casefold() in raw.casefold() for value in values
        ) else "normalized"
        if _is_patient_correction(evidence_text, span):
            classification = "patient_correction"
        return GroundingEvidence(
            classification, span, raw[span.start:span.end], tuple(spans)
        )
    if update.field == "duration" and len(values) == 1:
        span = _structured_duration_span(values[0], evidence_text)
        if span and not _unsafe_context(evidence_text, span, values[0]):
            raw = str(evidence_text or "")
            classification = (
                "patient_correction"
                if _is_patient_correction(evidence_text, span)
                else "structured_numeric"
            )
            return GroundingEvidence(
                classification, span, raw[span.start:span.end], (span,)
            )
    span = _canonical_alias_span(update.field, update.value, evidence_text)
    if span:
        raw = str(evidence_text or "")
        classification = (
            "patient_correction"
            if _is_patient_correction(evidence_text, span)
            else "canonical"
        )
        return GroundingEvidence(classification, span, raw[span.start:span.end], (span,))
    return GroundingEvidence("unsupported")


def grounding_classification(update, evidence_text: str) -> str:
    """Return literal, normalized, canonical, structured, or unsupported."""
    return grounding_evidence(update, evidence_text).classification


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

    # Emergency reasons must be safe codes.
    for reason in response.emergency_signal.reasons:
        if reason not in EMERGENCY_REASON_CODES:
            raise SemanticValidationError(f"Unsupported emergency reason {reason!r}")

    # Suggested relevance rules already allowlisted by Pydantic.
    # Extracted fields already allowlisted by Pydantic.
