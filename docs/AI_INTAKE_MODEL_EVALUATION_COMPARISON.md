# AI Intake Model Evaluation Comparison

Dataset: `mcc-ai-intake-eval-v2`, 20 static synthetic cases.

| Behavior | Phase C mock | DeepSeek run 1 | DeepSeek run 2 | Backend |
|---|---:|---:|---:|---|
| JSON valid | 100% | 100% | 100% | Parser rejects invalid output |
| Schema valid | 100% | 100% | 100% | Strict Pydantic schema |
| Semantic pass | 100% | 70% | 70% | Six unsupported/ungrounded attempts rejected |
| Question repeat rate | 0% | 0% | 0% | Answered-field questions rejected |
| Question selection correct | 100% | 75% | 50% | Informational quality metric |
| Prompt injection contained | 100% | 100% | 100% | Deterministic policy/validator |
| Premature completion contained | 100% | 100% | 100% | Completeness remains authoritative |
| Emergency downgrade contained | 100% | 100% | 100% | Deterministic emergency screen runs first |
| Provider failures | 0 | 0 | 0 | Safe provider error taxonomy |

Live-only finding: Arabic/CKB canonicalized values sometimes fail conservative lexical grounding. Failure forces clarification; it cannot populate unsupported clinical facts.

No aggregate “AI accuracy” or clinical score reported.
