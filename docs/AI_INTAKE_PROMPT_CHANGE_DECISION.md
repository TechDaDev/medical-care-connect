# AI Intake Prompt Change Decision

Decision: `NO PROMPT CHANGE REQUIRED`

Prompt remains `mcc-intake-v2`. Schema remains `mcc-intake-v2`.

Live baseline identified provider integration defects, not repeated prompt-policy failure:

1. DeepSeek V4 thinking mode exhausted bounded output.
2. Evidence UUIDs were sent as unsupported message metadata.
3. Server context omitted allowed relevance-rule codes.

Fixes disable thinking for bounded structured output, expose server-generated UUIDs in provider-visible content, and include authoritative relevance-rule-code metadata. No safety instruction, clinical role, schema, validator, or completion authority changed.

Model decision: `KEEP CURRENT MODEL` (`deepseek-v4-flash`). Full runs had 100% JSON/schema validity, zero provider failures/retries, and all safety containment thresholds passed. Question-selection variation remains informational; separate comparative evaluation required before model switch.
