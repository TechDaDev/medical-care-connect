# AI Intake Final Architecture

Status date: 2026-08-15

## Authority

Backend owns authorization, intake state, schema allowlists, completeness, emergency escalation, patient confirmation, submission, draft-record creation, ownership, doctor access, notifications, and audit events. DeepSeek advises only on wording, evidence-bound extraction, clarification, next-question suggestion, and review-summary wording.

DeepSeek cannot diagnose, treat, prescribe, downgrade emergency state, complete a consultation, assign a doctor, confirm for a patient, submit intake, or finalize a medical record.

## Runtime flow

Patient input first enters deterministic emergency screening. A detected emergency stops normal intake and bypasses provider execution. Otherwise, bounded history and server-owned field context are sent to the configured provider. Pydantic rejects shape or allowlist violations. Semantic validation rejects prohibited wording, invalid evidence ownership, unsupported extraction, and repeated answered-field questions. Language-aware normalization may prove evidence; it cannot create evidence. Deterministic completeness remains final authority for review, confirmation, and submission.

Accepted updates retain source message UUIDs and original text. Doctor projection exposes confirmed state, provenance, evidence, uncertainty, missing information, emergency state, AI-assistance disclaimer, and draft link—never raw prompts, provider output, diagnosis, or confidence percentages.

## Evaluation flow

`mcc-ai-intake-eval-v3` static synthetic split → explicit evaluator guard → deterministic emergency bypass or DeepSeek → Pydantic `mcc-intake-v2` → semantic/grounding validation → deterministic completeness → sanitized metrics report. Evaluator imports no patient/session/consultation ORM model and refuses database sources or application identifiers.

## Version decisions

- Prompt: `mcc-intake-v2` — kept.
- Schema: `mcc-intake-v2` — kept.
- Dataset: `mcc-ai-intake-eval-v3`.
- Emergency rules: `mcc-emergency-rules-v1` — unchanged because executable rules did not change.
- Model: `deepseek-v4-flash` — kept; larger evaluation did not justify comparison or change.

