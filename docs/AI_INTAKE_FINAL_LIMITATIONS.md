# AI Intake Final Limitations

Status date: 2026-08-15

- All 56 emergency rules lack qualified-clinician review evidence. Clinical status remains `UNREVIEWED`.
- Synthetic evaluation cannot establish real-world safety, diagnostic accuracy, treatment accuracy, prescribing accuracy, clinical equivalence, emergency sensitivity/specificity, or clinical validation.
- Phase E final live sample is 30 cases with 25 provider calls. Language subgroups remain small.
- One-shot final Iraqi Arabic grounding was 50%; final question selection was 50%. Rejection prevents unsupported persistence but reduces extraction utility.
- One-shot final Kurdish Sorani grounding was 0% despite 71.43% across each frozen validation run. Linguistic variants and borrowed vocabulary remain incomplete.
- Combined final question selection was 80%, below the 95% completion threshold.
- Final clarification samples were too small for broad claims.
- Language scoring detects script consistency, not fluency or dialect quality.
- Pricing is mutable; documented cost is an estimate range because cache-hit/miss token subdivision was not captured.
- Reviewer identity/qualification authenticity requires external operational verification; CSV validation proves metadata completeness, not identity.
- Phase E final blinded cases are consumed and must not be reused for future prompt tuning. A future prompt/model phase needs a newly protected final split.

Deferred: qualified multilingual clinician review; linguist-reviewed Iraqi/CKB canonical mappings; larger independent blinded language samples; cache-aware cost capture; new final dataset before future prompt/model change.
