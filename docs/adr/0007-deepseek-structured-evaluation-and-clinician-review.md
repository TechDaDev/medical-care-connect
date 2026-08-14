# ADR 0007: DeepSeek structured evaluation and clinician review isolation

Status: Accepted, 2026-08-14.

## Decision

Use static versioned synthetic fixtures for live DeepSeek evaluation. Refuse production, application identifiers, database sources, arbitrary provider endpoints/models, excessive cases, and non-temporary live reports. Store only sanitized technical metrics and safe error codes.

Use DeepSeek V4 non-thinking mode for bounded receptionist JSON. Embed server-generated evidence UUIDs in provider-visible message content; backend validates evidence ownership.

Keep emergency runtime enablement separate from clinician-review disposition. Export full synthetic worksheet; import validates metadata and emits evidence without executing or rewriting patterns.

## Consequences

Live evaluation cannot read MCC patient data. Unsafe provider attempts remain backend-contained. Clinician approval applies only to exact rule/ruleset version and cannot silently change runtime logic.
