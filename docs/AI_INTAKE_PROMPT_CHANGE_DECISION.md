# AI Intake Prompt Change Decision

Decision: `KEEP mcc-intake-v2`

Prompt remains `mcc-intake-v2`. Schema remains `mcc-intake-v2`.

Live baseline identified provider integration defects, not repeated prompt-policy failure:

1. DeepSeek V4 thinking mode exhausted bounded output.
2. Evidence UUIDs were sent as unsupported message metadata.
3. Server context omitted allowed relevance-rule codes.

Fixes disable thinking for bounded structured output, expose server-generated UUIDs in provider-visible content, and include authoritative relevance-rule-code metadata. No safety instruction, clinical role, schema, validator, or completion authority changed.

Model decision: `KEEP CURRENT MODEL` (`deepseek-v4-flash`). Full runs had 100% JSON/schema validity, zero provider failures/retries, and all safety containment thresholds passed. Question-selection variation remains informational; separate comparative evaluation required before model switch.

Phase E v4 evidence: three frozen validation runs and one final blinded run retained zero unsupported/hallucinated acceptance and complete injection/emergency containment. Final dialect quality remained below threshold (Iraqi grounding 50%, CKB grounding 0%, combined question selection 80%). Prompt stayed frozen because changing it after final exposure would invalidate blinding and dialect-only tuning lacked regression evidence. Future prompt work requires development/validation evidence plus a new blinded final split.
