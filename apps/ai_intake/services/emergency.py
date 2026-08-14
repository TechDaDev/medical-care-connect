"""Deterministic emergency screening backed by versioned, unreviewed rules.

Technical safety layer only. No sensitivity, specificity, or clinical-validation
claim is made. Original patient text remains stored by intake workflow.
"""

import re

from apps.ai_intake.emergency_rules.normalization import normalize_patient_text
from apps.ai_intake.emergency_rules.registry import rules_for_language

_NEGATION = {
    "en": ("no", "not", "never", "don't", "dont", "doesn't", "didn't", "without", "no history of"),
    "ar": ("لا", "ليس", "ما عندي", "ماكو", "بدون", "لم"),
    "ckb": ("نه", "نيم", "نییه", "نییە", "بێ"),
}
_FAMILY = {
    "en": ("my father", "my mother", "my brother", "my sister", "my husband", "my wife", "my friend", "my son", "my daughter"),
    "ar": ("ابي", "ابوي", "والدي", "امي", "والدتي", "اخي", "اختي", "زوجي", "زوجتي", "ابني", "ابنتي", "صديقي"),
    "ckb": ("باوکم", "دایکم", "براکم", "خوشکم", "هاوسه رم", "کوڕم", "کچم", "هاوڕێم"),
}
_HISTORICAL = {
    "en": ("years ago", "year ago", "months ago", "last year", "used to have", "history of"),
    "ar": ("قبل سنوات", "قبل سنه", "من زمان", "سابقا"),
    "ckb": ("ساڵ پێش", "پێشتر", "له ڕابردوودا"),
}
_HYPOTHETICAL = {
    "en": ("what does", "what if", "does it mean", "quoted"),
    "ar": ("ماذا يعني", "شنو يعني", "ماذا لو", "ما معنى"),
    "ckb": ("واتای چییه", "چی ده بێت ئه گه ر"),
}


def _language(text: str) -> str:
    if re.search(r"[ێڕڵۆەڤ]", text):
        return "ckb"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    return "en"


def _context_suppresses(text: str, phrase: str, language: str) -> bool:
    index = text.find(phrase)
    if index < 0:
        return False
    before = text[max(0, index - 56):index]
    whole = text[max(0, index - 72):min(len(text), index + len(phrase) + 40)]
    negation_scope = before if language == "en" else whole

    def contains(scope: str, token: str) -> bool:
        normalized_token = normalize_patient_text(token, language)
        return bool(re.search(
            rf"(?<!\w){re.escape(normalized_token)}(?!\w)", scope
        ))

    return (
        any(contains(negation_scope, token) for token in _NEGATION[language])
        or any(contains(before, token) for token in _FAMILY[language])
        or any(contains(whole, token) for token in _HISTORICAL[language])
        or any(contains(whole, token) for token in _HYPOTHETICAL[language])
    )


def screen_patient_input(text: str) -> dict:
    original = (text or "").strip()
    if not original:
        return {"detected": False, "level": "none", "reasons": []}
    language = _language(original)
    normalized = normalize_patient_text(original, language)
    ordered_rules = rules_for_language(language) + tuple(
        rule for rule in rules_for_language() if rule.language != language
    )
    for rule in ordered_rules:
        phrase = normalize_patient_text(rule.pattern, rule.language)
        if phrase not in normalized:
            continue
        if rule.suppressible and _context_suppresses(normalized, phrase, rule.language):
            continue
        return {"detected": True, "level": rule.severity, "reasons": [rule.code]}
    return {"detected": False, "level": "none", "reasons": []}
