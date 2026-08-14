"""Conservative multilingual normalization for deterministic matching."""

import re
import unicodedata

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_PUNCTUATION = re.compile(r"[^\w\s\u0600-\u06FF]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_patient_text(text: str, language: str | None = None) -> str:
    value = unicodedata.normalize("NFKC", text or "").casefold()
    value = value.replace("ـ", "")
    value = _ARABIC_DIACRITICS.sub("", value)
    value = value.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ی": "ي", "ك": "ک",
    }))
    value = value.replace("can’t", "can't").replace("cannot", "can't")
    value = _PUNCTUATION.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip()
