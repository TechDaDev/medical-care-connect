# AI Intake Final Language Evaluation

Status date: 2026-08-15

## Final blinded results

| Language | Cases | Provider calls | Semantic | Grounded extraction | Question selection | Language consistency | Mean latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| English | 7 | 6 | 83.33% | 100% | 100% | 100% | 2,552.40 |
| Arabic MSA | 5 | 4 | 100% | 100% | 100% | 100% | 3,207.67 |
| Iraqi Arabic | 5 | 4 | 0% | 0% | 100% | 100% | 3,459.59 |
| Kurdish Sorani | 5 | 4 | 75% | 50% | 100% | 100% | 4,124.64 |
| Mixed | 3 | 2 | 50% | n/a | n/a | 100% | 4,232.02 |

Emergency cases account for one local provider bypass per language group.

## Grounding findings

Phase C Arabic failures motivated classification into literal, normalized, canonical, structured, and unsupported evidence. Phase D normalization uses NFKC, Alef and Ya variants, Arabic/Persian Kaf, tatweel removal, diacritic removal, punctuation, and whitespace. Original evidence remains unchanged and bound by message UUID.

Field-scoped canonical aliases cover explicit headache/dizziness/nausea, duration/onset, severity, location, selected medication/allergy names, and explicit pregnancy statements across EN/Arabic/Iraqi/CKB forms. Multi-value extraction requires every value to be grounded. Empty structured values do not create facts; unsupported structured facts reject.

MSA improved safely to 100% grounded extraction in all frozen/final live runs. Iraqi live outputs repeatedly produced canonical values not safely provable from available sanitized evidence classifications; backend rejected them. No broad synonym or morphology relaxation was added without exact evidence. CKB accepted literal/Unicode-supported evidence while rejecting mismatched fields or unsupported onset claims. Safe rejection is preferred to invented meaning.

## Limitations

Language consistency checks script family, not linguistic naturalness. Dataset is synthetic and small per language. Iraqi and CKB canonical coverage remains incomplete and requires qualified linguistic/clinical review before expanding mappings. Rates are software-evaluation measures, not medical accuracy.

