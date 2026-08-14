"""Emergency-rule metadata. Rules are technical safeguards, not clinical claims."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class EmergencyRule:
    code: str
    language: Literal["en", "ar", "ckb"]
    severity: Literal["urgent", "emergency"]
    pattern: str
    pattern_type: Literal["normalized_phrase"] = "normalized_phrase"
    enabled: bool = True
    clinician_review_status: Literal["unreviewed", "reviewed", "approved", "rejected"] = "unreviewed"
    version: str = "2026-08-14"
    suppressible: bool = True
