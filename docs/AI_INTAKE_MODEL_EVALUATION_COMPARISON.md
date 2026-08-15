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

## Phase E v4 decision

Keep `deepseek-v4-flash`. Final 30-case blinded run completed 25 provider calls with zero failures/retries, 100% JSON/schema validity, zero unsafe acceptance, and complete hard-safety containment. Semantic pass was 60%, question selection 80%, Iraqi grounding 50%, and CKB grounding 0%. Those results do not justify a model switch without a controlled comparative development/validation study and new blind split; they instead keep Phase E software status `PARTIAL`.
