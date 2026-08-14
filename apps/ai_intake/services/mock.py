"""Deterministic local-E2E intake provider. Never available in production."""

import json

from apps.ai_intake.constants import INTAKE_FIELDS
from apps.ai_intake.services.base import AIProvider, AIProviderUnavailable


class DeterministicE2EProvider(AIProvider):
    """Small state-free provider driven only by server context and patient evidence."""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.calls = 0

    def generate_structured_response(self, messages, schema_name="intake_turn"):
        self.calls += 1
        context = next(
            json.loads(message["content"].split("\n", 1)[1])
            for message in messages
            if message.get("role") == "system"
            and '"missing_blocking_fields"' in message.get("content", "")
        )
        patient = next(message for message in reversed(messages) if message.get("role") == "patient")
        answer = patient["content"].strip()
        directive = answer.casefold()

        if "[mock:timeout]" in directive:
            raise AIProviderUnavailable("Synthetic provider timeout.", safe_code="provider_unavailable")
        if "[mock:rate-limit]" in directive:
            raise AIProviderUnavailable("Synthetic provider rate limit.", safe_code="provider_rate_limited")
        if "[mock:retry]" in directive and self.calls == 1:
            raise AIProviderUnavailable("Synthetic transient failure.", safe_code="provider_unavailable")
        if "[mock:invalid-json]" in directive:
            return "not-json"
        if "[mock:schema-error]" in directive:
            return {"conversation_status": "needs_more_information"}

        missing = list(context["missing_blocking_fields"])
        current_field = missing[0]
        remaining = missing[1:]
        normalized = directive.replace("[mock:retry]", "").strip() or "synthetic answer"
        value = [normalized] if INTAKE_FIELDS[current_field]["type"] == "list" else normalized
        update = {
            "field": current_field,
            "value": value,
            "source_message_ids": [patient["message_id"]],
            "certainty": "explicit",
        }
        if "[mock:unsafe-diagnosis]" in directive:
            update["field"] = "diagnosis"

        next_field = remaining[0] if remaining else None
        return {
            "conversation_status": "needs_more_information" if next_field else "propose_review",
            "patient_facing_message": (
                f"Thank you. {INTAKE_FIELDS[next_field]['question']}" if next_field
                else "Thank you. Please review the information before confirming."
            ),
            "next_question": (
                {"field": next_field, "text": INTAKE_FIELDS[next_field]["question"]}
                if next_field else None
            ),
            "extracted_updates": [update],
            "uncertain_fields": [],
            "suggested_relevant_fields": [],
            "emergency_signal": {"detected": False, "level": "none", "reasons": []},
            "summary_for_review": "Synthetic patient-reported intake for local E2E verification.",
        }
