# AI Intake Final Limitations

Status date: 2026-08-15

- All 56 emergency rules lack qualified-clinician review evidence. Clinical status remains `UNREVIEWED`.
- Synthetic evaluation cannot establish real-world safety, diagnostic accuracy, treatment accuracy, prescribing accuracy, clinical equivalence, emergency sensitivity/specificity, or clinical validation.
- Final live sample is 25 cases with 20 provider calls. Language subgroups are small.
- Iraqi Arabic grounding remained 0% in final because translated/canonical provider values lacked safe evidence proof under current mappings. Rejection prevented persistence but reduces extraction utility.
- Kurdish Sorani grounded extraction was 50%; linguistic variants and borrowed vocabulary remain incomplete.
- Question-selection varied across unchanged validation runs (100%, 100%, 80%); exact response identity is not expected.
- Clarification scoring had one applicable case per run and varied 100%, 100%, 0%; sample too small for broad claims.
- Language scoring detects script consistency, not fluency or dialect quality.
- Pricing is mutable; documented cost is an estimate range because cache-hit/miss token subdivision was not captured.
- Reviewer identity/qualification authenticity requires external operational verification; CSV validation proves metadata completeness, not identity.
- Final blinded cases are now consumed and must not be reused for future prompt tuning. A future prompt/model phase needs a newly protected final split.

Deferred: qualified multilingual clinician review; linguist-reviewed Iraqi/CKB canonical mappings; larger independent blinded language samples; cache-aware cost capture; new final dataset before future prompt/model change.

