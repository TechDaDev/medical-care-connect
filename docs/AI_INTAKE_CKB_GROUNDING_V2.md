# Kurdish Sorani Grounding V2

Scope is bounded evidence verification for existing intake fields.

Normalization uses NFKC and removes bidi/zero-width formatting safely. Arabic/Persian Kaf and Ya variants normalize for matching; meaningful Kurdish letters such as `ە`, `ۆ`, `ڕ`, `ڵ`, and `ێ` remain distinct. Token spans come from deterministic Unicode-aware scanning, not whitespace splitting or an LLM tokenizer.

Field-scoped mappings cover complaint, symptom, onset, duration, severity, location, medication, allergy, negation, family/history attribution, and correction. Borrowed Arabic/English medication terms require explicit evidence. No fuzzy drug or diagnosis mapping exists.

Every accepted canonical value retains message ownership and an original-text span. Clause-local negation and family context prevent polarity or attribution inversion. Latest explicit correction may replace structured state while source messages remain preserved. Unsupported mappings fail closed.
