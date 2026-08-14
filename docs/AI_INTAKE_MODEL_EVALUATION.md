# AI Intake Model Evaluation

Command defaults to deterministic mock mode:

```bash
python manage.py evaluate_ai_intake --provider mock --output-json /tmp/ai-intake-eval.json
```

Dataset must declare `synthetic: true`. Report contains run ID/time, commit, prompt/schema/dataset versions, provider/model, temperature, limits, aggregate metrics, and sanitized per-case identifiers/results. Raw narratives, prompts, provider payloads, secrets, and patient data are excluded.

Metrics cover JSON/schema validity, semantic validation, grounded extraction, unsupported/hallucinated field rejection, premature-completion rejection, prompt-injection resistance, emergency-downgrade rejection, token counts, latency, and retries.

Provider metrics report provider behavior, not backend enforcement. Mock scenarios intentionally include premature-completion and emergency-downgrade attempts, so those rates are `0.0`; separate backend tests prove both unsafe suggestions are rejected or overridden. A low mock metric is evidence of defense-in-depth coverage, not a release failure or clinical claim.
