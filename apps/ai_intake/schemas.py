"""
Strict DeepSeek intake-turn response schema and semantic validation.

Rules:
- unknown keys rejected (Pydantic forbid);
- field names allowlisted from constants.INTAKE_FIELDS;
- extracted updates carry evidence message IDs;
- certainty is explicit | inferred | uncertain;
- emergency_signal may only increase caution — never reduce deterministic result;
- no diagnosis / treatment / prescription fields exist anywhere in the schema.
"""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from apps.ai_intake.constants import (
    CONDITIONAL_RELEVANCE_RULES,
    INTAKE_FIELDS,
    VALID_CERTAINTY,
)


class ExtractedFieldUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    field: str
    value: str | list[str] | bool | int | None
    source_message_ids: list[UUID] = Field(default_factory=list)
    certainty: Literal["explicit", "inferred", "uncertain"] = "explicit"

    @model_validator(mode="after")
    def validate_field_allowlist(self):
        if self.field not in INTAKE_FIELDS:
            raise ValueError(f"Unsupported intake field: {self.field!r}")
        return self


class EmergencySignal(BaseModel):
    model_config = {"extra": "forbid"}

    detected: bool = False
    level: Literal["none", "urgent", "emergency"] = "none"
    reasons: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_reasons(self):
        for reason in self.reasons:
            if not (1 <= len(reason) <= 80):
                raise ValueError("Emergency reason codes must be short safe codes")
        return self


class NextQuestion(BaseModel):
    model_config = {"extra": "forbid"}

    field: Optional[str] = None
    text: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_field_and_text(self):
        if self.field is not None and self.field not in INTAKE_FIELDS:
            raise ValueError(f"Unsupported next-question field: {self.field!r}")
        if self.field is None and self.text is None:
            raise ValueError("next_question requires field or text")
        if self.field is not None and not self.text:
            raise ValueError("next_question with a field requires a text question")
        return self


class IntakeTurnResponse(BaseModel):
    """Strict structured response from DeepSeek for a single intake turn.

    The AI may propose completion via conversation_status=propose_review.
    The deterministic backend completeness gate is the final authority.
    """

    model_config = {"extra": "forbid"}

    conversation_status: Literal["needs_more_information", "propose_review"]
    patient_facing_message: str = Field(..., min_length=1, max_length=1000)
    next_question: Optional[NextQuestion] = None
    extracted_updates: list[ExtractedFieldUpdate] = Field(default_factory=list, max_length=8)
    uncertain_fields: list[str] = Field(default_factory=list, max_length=8)
    suggested_relevant_fields: list[str] = Field(default_factory=list, max_length=4)
    emergency_signal: EmergencySignal = Field(default_factory=EmergencySignal)
    summary_for_review: Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def validate_uncertain_fields_allowlist(self):
        for name in self.uncertain_fields:
            if name not in INTAKE_FIELDS:
                raise ValueError(f"Unsupported uncertain field: {name!r}")
        return self

    @model_validator(mode="after")
    def validate_suggested_relevant_fields(self):
        for rule in self.suggested_relevant_fields:
            if rule not in CONDITIONAL_RELEVANCE_RULES:
                raise ValueError(f"Unsupported relevance rule: {rule!r}")
        return self

    @model_validator(mode="after")
    def validate_next_question_requirement(self):
        if self.conversation_status == "needs_more_information" and self.next_question is None:
            raise ValueError("next_question is required when needs_more_information")
        if self.conversation_status == "propose_review" and self.next_question is not None:
            raise ValueError("next_question must be null when propose_review")
        return self

    @model_validator(mode="after")
    def validate_no_duplicate_extracted_fields(self):
        seen = set()
        for update in self.extracted_updates:
            if update.field in seen:
                raise ValueError(f"Duplicate extracted field: {update.field}")
            seen.add(update.field)
        return self