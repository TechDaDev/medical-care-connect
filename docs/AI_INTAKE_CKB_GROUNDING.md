# AI Intake Kurdish Sorani Grounding

Status date: 2026-08-15

## Scope

Phase E adds conservative `ckb` evidence recognition. Original Kurdish Sorani text remains authoritative and unchanged.

## Normalization and morphology

Matching applies NFKC, Arabic/Persian digit conversion, Arabic/Persian Kaf and Ya normalization, zero-width/diacritic/tatweel removal, repeated-character collapse, punctuation separation, and whitespace normalization. Field-scoped aliases recognize bounded common Sorani forms and attached possessive/copular morphology for symptoms, duration, onset, severity, location, medication, allergy, previous episode, and progression.

The matcher returns an original-text evidence span. It does not use substring-only acceptance, global transliteration, free translation, stemming across fields, diagnosis inference, or medication guessing.

## Safety behavior

- Negated, family-member, historical, and hypothetical context remains unsupported.
- Unknown drug names and vague values remain unsupported.
- Canonical recognition must bind to a specific source span.
- Failure rejects the update and requests clarification; no unsupported value persists.

## Evaluation

Broadened pre-hardening validation grounding: 4/7, 57.14%. Frozen post-hardening validation: 71.43% in all three runs with 100% semantic validation and zero unsafe acceptance. One-shot final blinded CKB result: semantic 42.86%, grounding 0%, question selection 100%, zero unsupported/hallucinated acceptance, and complete injection/emergency containment.

Final grounding regression blocks COMPLETE status. Future work needs linguist-reviewed variants and a new blinded split; consumed final cases cannot be tuning data.
