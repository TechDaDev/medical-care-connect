# AI Intake Iraqi Arabic Grounding

Status date: 2026-08-15

## Scope

Phase E adds conservative Iraqi Arabic evidence recognition for intake extraction. It does not translate free text, infer diagnoses, prescribe, or relax backend semantic validation.

## Pipeline

Original patient text is retained. A matching-only view applies Unicode NFKC, Arabic/Persian digit conversion, Alef/Ya/Kaf normalization, tatweel/diacritic/zero-width removal, repeated-character collapse, punctuation separation, and whitespace normalization. Token offsets remain mapped to original text.

Field-scoped aliases cover chief complaint/symptoms, duration, onset, severity, location, current medication, allergy, previous episode, and progression. Examples include Iraqi expressions such as `صارلي`, `من البارحة`, `كلش قوي`, anatomical clitics, and common paracetamol/penicillin forms. Alias evidence cannot cross field boundaries.

## Safety behavior

- Literal and normalized matches require token boundaries.
- Canonical values require an explicit alias in the same field.
- Negated, family-member, historical, and hypothetical context is rejected.
- Vague duration and unknown medication names remain unsupported.
- Match result includes classification plus original-text start/end offsets.
- Unsupported values force rejection/clarification; they are never guessed or persisted.

## Evaluation

Broadened pre-hardening validation grounding: 3/7, 42.86%. Frozen post-hardening validation across three runs: 71.43%, 85.71%, 85.71%; unsupported and hallucinated acceptance stayed zero. One-shot final blinded Iraqi result: semantic 50%, grounding 50%, question selection 50%, zero unsupported/hallucinated acceptance, and complete injection/emergency containment.

Final quality remains below release threshold. Mapping is a technical guard, not linguistic or clinical validation.
