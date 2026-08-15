# AI Intake Final Evaluation

Status date: 2026-08-15

## Dataset and procedure

`mcc-ai-intake-eval-v3` contains 100 static synthetic cases: development 50, validation 25, final blinded 25. Languages: EN 30, Arabic MSA 20, Iraqi Arabic 20, Kurdish Sorani 20, mixed 10. Final metadata is `blinded=true` and `tuning_allowed=false`.

Prompt-v2 baseline ran before prompt consideration. A validation composition defect (missing prompt-injection and premature-completion categories) was found before any final-provider run; split composition was corrected, tests frozen it, and three independent unchanged validation runs followed. Final blinded ran once. No final failure drove prompt, grounding, or dataset edits.

## Development

Deterministic mock: 50 cases. It verifies guards, scoring, emergency bypass, completeness containment, schema plumbing, languages, and report sanitization. Mock output is not provider-quality evidence.

## Frozen validation runs

| Metric | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Cases / provider calls / bypasses | 25 / 20 / 5 | 25 / 20 / 5 | 25 / 20 / 5 |
| Provider failures | 0 | 0 | 0 |
| JSON / schema / language | 100% / 100% / 100% | 100% / 100% / 100% | 100% / 100% / 100% |
| Semantic | 65% | 70% | 70% |
| Grounded extraction | 57.14% | 57.14% | 57.14% |
| Question selection | 100% | 100% | 80% |
| Valid clarification | 100% | 100% | 0% |
| Repeat rate | 0% | 0% | 0% |
| Input / output / total tokens | 34,113 / 5,810 / 39,923 | 34,113 / 6,062 / 40,175 | 34,113 / 5,859 / 39,972 |
| Mean / p50 / p95 / max ms | 3,444.54 / 3,041.75 / 4,907.39 / 7,755.67 | 3,206.18 / 2,910.99 / 4,624.14 / 5,525.99 | 3,181.28 / 2,996.65 / 4,311.76 / 4,929.73 |

Across each run: unsupported acceptances 0, accepted hallucinations 0, prompt-injection containment 100%, premature-completion containment 100%, emergency containment/provider bypass 100%, hidden-prompt/provider-secret leakage 0 observed.

## Final blinded acceptance

25 attempted/completed; 20 provider calls, 5 deterministic emergency bypasses, 0 provider failures. JSON 100%; schema 100%; semantic 65%; grounded extraction 57.14%; language 100%; question selection 100%; valid clarification 100%; repeats 0%. One hallucination attempt was rejected; accepted hallucinations 0. Two injection inputs were contained. One premature-completion input was contained. Five emergency-downgrade inputs were contained and bypassed provider.

Tokens: 34,123 input, 6,183 output, 40,306 total. Latency: mean 3,347.30 ms, p50 3,221.77 ms, p95 5,018.52 ms, max 5,349.91 ms. Retry-added latency: none recorded; retry count 0.

## Decisions

`KEEP mcc-intake-v2`. Schema/language/repeat behavior was stable; question-selection variance was measured but did not show repeated provider defect sufficient to justify prompt-v3 risk. Grounding misses were conservatively rejected by backend and are not solved through prompt authority.

`KEEP CURRENT MODEL` (`deepseek-v4-flash`). Hard safety and schema targets passed; no evidence justified model comparison.

## Cost

Official DeepSeek pricing checked 2026-08-15: `deepseek-v4-flash` $0.0028/M cached input, $0.14/M uncached input, $0.28/M output. Provider reports did not expose cache-hit/miss subdivision to this evaluator, so cost is a range, not a billed amount.

Three frozen validation runs plus final: 136,462 input and 23,914 output tokens; estimated $0.00708 (all input cache hit) to $0.02580 (all input cache miss). Including the pre-freeze 25-case v3 baseline: 170,529 input and 29,951 output; estimated $0.00886 to $0.03226. Source: <https://api-docs.deepseek.com/quick_start/pricing>.

