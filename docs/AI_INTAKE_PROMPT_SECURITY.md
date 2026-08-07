# AI Intake Prompt Security

Prompt version: `mcc-intake-v2`. Schema version: `mcc-intake-v2`.

## Layered prompt architecture

`build_ai_messages` assembles four explicit layers:

1. **System policy** (`SYSTEM_POLICY_PROMPT`) — receptionist scope, prohibited
   diagnosis/treatment, emergency limitations, output contract, injection
   resistance, language behavior.
2. **Server-controlled intake context** — allowlisted fields, deterministic
   missing fields, question count/budget, schema version, allowed emergency
   reason codes. Delivered as a separate system message (`server_intake_context`)
   so patient content can never override it.
3. **Conversation evidence** — bounded, role-separated patient/assistant
   messages treated strictly as data. Each message carries its DB `message_id`
   so the provider can cite real evidence.
4. **Output contract** — exact JSON schema; forbids diagnosis, treatment,
   prescription, extra keys, markdown, hidden reasoning.

Server context is never merged into a user-role message.

## Injection resistance

Patient text is medical-intake data, never instructions. Deterministic tests
cover: show system prompt, hidden schema, role override, forced completion,
emergency bypass, diagnosis, prescription, fabricated JSON state, another
patient's data, provider key, and malicious markdown/HTML. Expected: the text
remains in the patient role only, no state override, no unsafe field stored, no
diagnosis/treatment output, safe follow-up.

## Response schema

`IntakeTurnResponse` (Pydantic, `extra="forbid"`):

- `conversation_status`: `needs_more_information | propose_review`
- `patient_facing_message`
- `next_question`: `{field, text}` (allowlisted field)
- `extracted_updates`: `{field, value, source_message_ids, certainty}`
- `uncertain_fields`
- `suggested_relevant_fields` (allowlisted rule codes)
- `emergency_signal`: `{detected, level, reasons}` (safe reason codes)
- `summary_for_review`

Unknown keys, unknown fields, wrong types, invalid enums, and duplicate
extracted fields are rejected by Pydantic.

## Semantic validation

After Pydantic, `validate_semantics` rejects:

- prohibited diagnosis/treatment/prescription/prompt-disclosure wording in
  patient-facing content;
- evidence ids that do not belong to the session;
- explicit/inferred extractions that are not lexically grounded in the cited
  evidence (hallucination guard);
- values whose type does not match the canonical field type;
- next questions for already-answered fields;
- unsupported emergency reason codes.

See `docs/AI_INTAKE_DATA_PROVENANCE.md` and `docs/AI_INTAKE_PROVIDER_FAILURES.md`.
