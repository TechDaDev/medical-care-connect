# AI Intake Information Schema

The canonical server-side intake schema lives in `apps/ai_intake/constants.py`
(`INTAKE_FIELDS`). Every AI-extractable or patient-reportable field must appear
there; its name is the only value accepted in AI output, `missing_fields`,
corrections, and collected metadata (allowlist enforcement in schema and
semantic validation).

## Field registry (subset)

| Field | Type | Universal | Conditional |
| --- | --- | --- | --- |
| chief_complaint | text | yes | no |
| symptoms | list | yes | no |
| onset | text | yes (pair) | no |
| duration | text | yes (pair) | no |
| progression | text | no | yes |
| severity | text | yes | no |
| location | text | no | yes |
| character | text | no | no |
| triggers | text | no | no |
| relieving_factors | text | no | no |
| associated_symptoms | list | no | no |
| previous_episodes | text | no | yes |
| past_medical_history | text | yes | no |
| surgical_history | text | no | no |
| current_medications | list | yes | no |
| medication_changes | text | no | no |
| allergies | list | yes | no |
| allergy_reactions | text | no | no |
| family_history | text | no | yes |
| social_history | text | no | no |
| substance_use | text | no | yes |
| pregnancy_possible | boolean | no | yes |
| recent_travel_exposure | text | no | yes |
| previous_tests_treatment | text | no | no |
| warning_signs | text | no | no |
| additional_concerns | text | no | no |

`onset`/`duration` form a timing pair: answering either satisfies both.

## Per-field metadata

Each field is stored under `AIIntakeSession.field_metadata` as:

```json
{
  "value": "...",
  "status": "missing|answered|unknown|declined|not_applicable|uncertain",
  "source": "patient_message|patient_profile|intake_extraction|patient_correction",
  "confidence": "low|medium|high",
  "evidence_message_ids": ["uuid"],
  "confirmed_by_patient": false
}
```

- `confidence` is an internal value used only for uncertainty labeling. It is
  never presented as clinical certainty.
- `evidence_message_ids` reference `AIIntakeMessage` rows in the same session.
- `confirmed_by_patient` flips to `true` at confirmation.

## Special internal gates

- `emergency_screen_completed` — deterministic emergency screening always runs
  before any normal-flow persistence.
- `patient_confirmed` — patient confirmation of the review summary is required
  before submission.

See `docs/AI_INTAKE_COMPLETENESS.md` for required vs conditional rules.
