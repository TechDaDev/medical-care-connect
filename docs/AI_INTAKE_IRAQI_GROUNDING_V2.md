# Iraqi Arabic Grounding V2

Scope is evidence verification for allowlisted intake fields, not translation or clinical inference.

Pipeline: raw patient text → NFKC/script normalization → field-scoped phrase recognition → canonical candidate → original-text evidence span → semantic validation.

Supported bounded categories include complaint, symptoms, onset, duration, severity, location, medication, allergy, negation, family/history attribution, and correction. Arabic/Persian and Western digits support structured durations. Vague phrases such as `من كم يوم`, `من زمان`, and `صارلي فترة` cannot support exact numeric values. Onset and duration remain field-scoped.

Negation is clause-local. Family statements cannot populate patient history/allergy. Latest explicit correction may supersede prior structured state while original messages remain immutable. Drug matching uses explicit aliases or exact normalized forms; no fuzzy medical guessing. Adverse effects do not become allergies without explicit allergy language.

Accepted evidence classifications: `literal`, `normalized`, `canonical_alias`, `structured_numeric`, or `patient_correction`. `unsupported` is fail-closed.
