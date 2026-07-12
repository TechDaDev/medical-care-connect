from typing import Optional

from pydantic import BaseModel, Field, model_validator


class IntakeTurnResponse(BaseModel):
    """Structured response from the AI for a single intake turn."""

    conversation_status: str = Field(
        ..., pattern=r"^(needs_more_information|ready_for_review)$"
    )
    patient_facing_message: str = Field(..., min_length=1)
    next_question: Optional[str] = Field(None)
    emergency_detected: bool = False
    emergency_level: str = Field(
        "none", pattern=r"^(none|warning|urgent|emergency)$"
    )
    emergency_reasons: list[str] = Field(default_factory=list)
    collected_data: "CollectedData" = Field(default_factory=lambda: CollectedData())
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_question_required_when_needs_info(self):
        if self.conversation_status == "needs_more_information" and not self.next_question:
            raise ValueError("next_question is required when needs_more_information")
        if self.conversation_status == "ready_for_review" and self.next_question is not None:
            raise ValueError("next_question must be null when ready_for_review")
        return self


class CollectedData(BaseModel):
    """Medical intake data collected during the session."""

    chief_complaint: Optional[str] = None
    symptoms: list[str] = Field(default_factory=list)
    symptom_duration: Optional[str] = None
    severity: Optional[int] = Field(None, ge=0, le=10)
    associated_symptoms: list[str] = Field(default_factory=list)
    chronic_conditions: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    surgical_history: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    pregnancy_status: Optional[str] = None
    relevant_test_results: list[str] = Field(default_factory=list)
    additional_information: list[str] = Field(default_factory=list)
