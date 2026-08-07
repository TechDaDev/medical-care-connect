# AI Intake Architecture

Phase A of the AI intake feature hardens the DeepSeek receptionist that
interviews a patient before doctor review. This document describes the full
architecture, authority boundaries, and safety controls. It is part of the
AI Intake Phase A acceptance evidence set.

## Purpose

The AI receptionist collects patient-reported information, asks relevant
follow-up questions, organizes answers into a structured intake, identifies
missing or uncertain information, stops and escalates on deterministic
emergency rules, presents a reviewable summary, and creates a clearly labeled,
unverified medical-record draft for the assigned doctor. It does not diagnose,
prescribe, determine clinical outcomes, or silently convert AI text into
doctor-authored medical content.

## Flow

1. Patient creates/opens a consultation.
2. Patient starts the intake session (`start_intake_session`).
3. Patient answers questions (`process_intake_answer`).
   - Deterministic emergency screen runs first.
   - Idempotency check by `client_request_id`.
   - Patient message saved once with a transactional sequence number.
   - Bounded, role-separated history is sent to the provider.
   - Provider output passes schema (Pydantic) and semantic validation.
   - Extracted updates merge into `field_metadata` with provenance.
   - Backend recomputes completeness; provider `propose_review` is advisory.
4. When the backend gate passes, the session enters `awaiting_patient_review`.
5. Patient reviews the summary, corrects values, marks fields unknown/declined,
   and confirms (`confirm_intake`).
6. Patient submits to the doctor (`submit_intake`):
   - atomically creates one medical-record draft;
   - transitions the consultation to `doctor_review`;
   - notifies the assigned doctor once;
   - audits once.
7. The doctor opens the doctor-safe intake projection and the draft.

## Components

- `apps/ai_intake/models.py` — session, message, idempotency ledger.
- `apps/ai_intake/constants.py` — canonical field registry + completion policy.
- `apps/ai_intake/schemas.py` — strict Pydantic provider response schema.
- `apps/ai_intake/prompts.py` — layered prompt architecture (version
  `mcc-intake-v2`).
- `apps/ai_intake/services/state.py` — centralized legal state transitions.
- `apps/ai_intake/services/completeness.py` — deterministic completeness engine.
- `apps/ai_intake/services/emergency.py` — deterministic emergency screening.
- `apps/ai_intake/services/semantic_validation.py` — semantic + hallucination guard.
- `apps/ai_intake/services/history.py` — bounded history and token budget.
- `apps/ai_intake/services/base.py` — provider error taxonomy + retry policy.
- `apps/ai_intake/services/deepseek.py` — OpenAI-compatible DeepSeek provider.
- `apps/ai_intake/services/intake.py` — deterministic orchestration.
- `apps/ai_intake/views.py`, `serializers.py`, `urls.py` — patient API.
- `apps/medical_records/services.py` — `generate_draft_from_intake`.
- `apps/consultations/doctor_serializers.py` — `DoctorIntakeSerializer`.

## Key settings

```
AI_INTAKE_ENABLED=false
AI_INTAKE_PROVIDER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=...
DEEPSEEK_TIMEOUT_SECONDS=...
DEEPSEEK_MAX_TOKENS=1200
DEEPSEEK_TEMPERATURE=0.2
AI_INTAKE_MAX_QUESTIONS=12
AI_INTAKE_MAX_ANSWER_LENGTH=2000
AI_INTAKE_MAX_ASSISTANT_LENGTH=1000
AI_INTAKE_MAX_HISTORY_MESSAGES=20
AI_INTAKE_MAX_PROMPT_TOKENS=6000
AI_INTAKE_MAX_OUTPUT_TOKENS=1200
AI_INTAKE_MAX_SESSION_TOKENS=40000
AI_INTAKE_MAX_RETRIES=2
```

See `docs/AI_INTAKE_PROVIDER_FAILURES.md` for failure behavior and
`docs/AI_INTAKE_PERMISSION_MATRIX.md` for access rules.
