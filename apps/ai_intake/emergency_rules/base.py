"""Emergency-rule metadata. Rules are technical safeguards, not clinical claims."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal


@dataclass(frozen=True, slots=True)
class EmergencyRule:
    code: str
    language: Literal["en", "ar", "ckb"]
    severity: Literal["urgent", "emergency"]
    pattern: str
    pattern_type: Literal["normalized_phrase"] = "normalized_phrase"
    enabled: bool = True
    clinician_review_status: Literal[
        "unreviewed", "approved", "approved_with_changes", "rejected",
        "needs_more_evidence",
    ] = "unreviewed"
    version: str = "2026-08-14"
    suppressible: bool = True

    @property
    def rule_id(self) -> str:
        identity = f"{self.language}:{self.code}:{self.pattern}:{self.version}"
        return f"{self.language}-{self.code}-{sha256(identity.encode()).hexdigest()[:12]}"
