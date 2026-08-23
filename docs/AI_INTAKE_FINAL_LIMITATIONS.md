# AI Intake Final Limitations

Status date: 2026-08-23

- All 56 emergency rules lack qualified-clinician review evidence. Clinical status remains `UNREVIEWED`.
- Synthetic evaluation cannot establish real-world safety, diagnostic accuracy, treatment accuracy, prescribing accuracy, clinical equivalence, emergency sensitivity/specificity, or clinical validation.
- Phase F final live sample is 40 synthetic cases with 36 provider calls and four deterministic emergency bypasses. Language subgroups remain small.
- One-shot final Iraqi Arabic grounding was 62.5%, below 80%. Kurdish Sorani was 75%, below 80%. Safe rejection prevents unsupported persistence but reduces extraction utility.
- Accepted backend question target correctness was 100%, while raw provider target correctness was 50%; deterministic fallback therefore remains operationally important.
- Overall final grounding was 66.67% and semantic validity was 80.56%. English, MSA, and mixed subsets also have small denominators and are informational.
- Final clarification samples were too small for broad claims.
- Language scoring detects script consistency, not fluency or dialect quality.
- Pricing is mutable; documented cost is an estimate range because cache-hit/miss token subdivision was not captured.
- Reviewer identity/qualification authenticity requires external operational verification; CSV validation proves metadata completeness, not identity.
- Phase F final blinded cases are consumed and must not be reused for future prompt tuning. Generator-based blinding is procedural, not independent human blinding. A future prompt/model phase needs a newly protected final split.

Deferred: qualified multilingual clinician review; linguist-reviewed Iraqi/CKB mappings and question wording; larger independently curated blinded samples; cache-aware cost capture; new final dataset before future prompt/model change.
