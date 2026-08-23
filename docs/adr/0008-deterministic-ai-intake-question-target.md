# ADR 0008: Deterministic AI Intake Question Target

Status: accepted

## Context

Previously DeepSeek selected both next field and wording. Phase E final target correctness was 80%; a model-selected field could diverge from deterministic missing blocking state.

## Decision

Completeness engine produces ordered allowed fields and one preferred field. DeepSeek may word preferred field only. Backend rejects any other target and supplies allowlisted localized fallback. Emergency and review states remain backend-owned.

## Consequences

Safety improves because prompt injection, optional-field diversion, and repeated completed fields cannot change target authority. UX retains provider wording when correct and receives deterministic wording otherwise. API schema remains compatible; audit/evaluation records fallback behavior.

## Rollback

Revert target enforcement and prompt context together. Keep schema compatibility. Rollback requires explicit security review because it restores model-driven target authority.
