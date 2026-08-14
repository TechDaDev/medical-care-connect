"""Emergency ruleset registry with truthful governance metadata."""

from .ar import RULES as AR_RULES
from .ckb import RULES as CKB_RULES
from .en import RULES as EN_RULES

RULESET_VERSION = "mcc-emergency-rules-v1"
ALL_RULES = tuple(EN_RULES + AR_RULES + CKB_RULES)


def rules_for_language(language: str | None = None):
    normalized = "ckb" if language in {"ckb", "ku"} else language
    if normalized in {"en", "ar", "ckb"}:
        return tuple(rule for rule in ALL_RULES if rule.language == normalized and rule.enabled)
    return tuple(rule for rule in ALL_RULES if rule.enabled)
