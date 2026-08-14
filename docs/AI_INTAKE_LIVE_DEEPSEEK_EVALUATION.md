# AI Intake Live DeepSeek Evaluation

Evaluation date: 2026-08-14. Dataset contains static synthetic cases only. No application ORM objects or production data used.

## Configuration

- Provider/model: DeepSeek / `deepseek-v4-flash`
- Official endpoint: `https://api.deepseek.com/chat/completions`
- Prompt/schema: `mcc-intake-v2` / `mcc-intake-v2`
- Dataset: `mcc-ai-intake-eval-v2`
- Cases: 20; EN 11, AR 6, CKB 3
- Temperature: 0.2
- Output bound: 800 tokens; timeout: 45 seconds; retries: 2
- Official docs checked 2026-08-14: [chat completion](https://api-docs.deepseek.com/api/create-chat-completion), [models and pricing](https://api-docs.deepseek.com/quick_start/pricing), [rate limits](https://api-docs.deepseek.com/quick_start/rate_limit), [errors](https://api-docs.deepseek.com/quick_start/error_codes/)

## Baseline defects and fixes

Initial 3-case smoke returned three `provider_response_truncated` failures. DeepSeek V4 defaults to thinking mode; bounded structured output now explicitly disables thinking.

Next smoke produced valid JSON but invalid evidence UUIDs. Provider wire format now embeds server-generated message UUIDs into content and removes unsupported message metadata.

Next schema failure used field name `severity` where relevance-rule code was required. Server context now supplies authoritative relevance-rule-code allowlist. Validators were not weakened.

Final smoke: 3/3 completed, JSON/schema 100%, provider failures 0, retries 0, 5,891 tokens.

## Full reproducibility results

Run 1 ID `62423a73-7a82-4867-9d37-f03d0e6a6879`:

- Attempted/completed/provider failures: 20/20/0
- JSON/schema/semantic: 100% / 100% / 70%
- Grounded extraction: 83.33%
- Unsupported attempts/rejection: 6 / 100%
- Hallucination attempts/rejection: 0 / 100%
- Prompt-injection attempts/containment: 0 / 100%
- Premature completion attempts/containment: 0 / 100%
- Emergency downgrade attempts/containment: 0 / 100%
- Question repeats/rate: 0 / 0%
- Question-selection correctness: 75%
- Language consistency: 100%
- Tokens input/output/total: 33,840 / 5,545 / 39,385
- Latency average/p50/p95/max: 2,901.10 / 2,736.00 / 3,970.29 / 4,076.61 ms
- Retries: 0

Run 2 ID `b8f5273c-58da-434f-bd8c-4c35c1aeea87`:

- Attempted/completed/provider failures: 20/20/0
- JSON/schema/semantic: 100% / 100% / 70%
- Grounded extraction: 83.33%
- Unsupported attempts/rejection: 6 / 100%
- Hallucination attempts/rejection: 0 / 100%
- Prompt-injection attempts/containment: 0 / 100%
- Premature completion attempts/containment: 0 / 100%
- Emergency downgrade attempts/containment: 0 / 100%
- Question repeats/rate: 0 / 0%
- Question-selection correctness: 50%
- Language consistency: 100%
- Tokens input/output/total: 33,840 / 5,433 / 39,273
- Latency average/p50/p95/max: 2,765.25 / 2,638.23 / 3,962.62 / 4,507.61 ms
- Retries: 0

## Language results

Run 1: EN 11 cases, schema 11, semantic 10, language-consistent 11; AR 6, schema 6, semantic 3, language-consistent 6; CKB 3, schema 3, semantic 1, language-consistent 3.

Run 2 repeated same schema, semantic, and language counts. Strict lexical grounding contained six stable canonicalization/translation mismatches. These are safe false negatives that may cause follow-up questions; validators remain unchanged.

Question-selection variation occurred only in ambiguous/CKB cases. No repeated answered-field question occurred.

## Cost

Official 2026-08-14 `deepseek-v4-flash` prices: cache-miss input $0.14/M tokens; output $0.28/M tokens. Cache split was not recorded, so conservative cache-miss estimate used.

- Run 1 estimated maximum: $0.00629
- Run 2 estimated maximum: $0.00626
- Two full runs estimated maximum: $0.01255

## Boundary

Results measure technical receptionist behavior only. They do not measure diagnostic accuracy, treatment accuracy, emergency sensitivity/specificity, clinical safety, or doctor equivalence.
