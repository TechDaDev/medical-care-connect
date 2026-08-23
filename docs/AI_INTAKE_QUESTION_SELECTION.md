# AI Intake Question Selection

Backend owns target selection. Completeness engine returns ordered `allowed_next_fields` and one `preferred_next_field` from existing field metadata and registry priority.

Priority:

1. emergency stop: no provider call and no next question;
2. missing or uncertain blocking field;
3. relevant conditional field;
4. non-blocking field when policy permits;
5. review only when complete.

Provider receives allowed/preferred context and may word preferred target. A different, completed, optional-before-blocking, or otherwise unauthorized target is rejected. Backend emits allowlisted fallback wording and records fallback in structured/audit evidence. Valid uncertainty clarification is distinct from unnecessary repetition.

Compatibility: response schema remains `mcc-intake-v2`; prompt is `mcc-intake-v3`. Existing clients continue consuming `next_question`. Rollback can restore model target choice, but would weaken deterministic authority and is not recommended.
