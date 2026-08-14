# AI Intake Phase B Security

Trust boundaries: patient browser, MCC backend, database, optional model provider, doctor browser. Main threats: IDOR, transferred-case leakage, hidden prompt/provider leakage, prompt injection, model-driven state changes, evidence spoofing, emergency downgrade, stored XSS, and evaluation data exfiltration.

Controls: approved assigned-doctor queryset, 404 concealment, server-derived policy, safe serializer allowlist, same-session evidence-ID filtering, React escaping, backend emergency/completeness authority, synthetic-only evaluator, explicit live gates, bounded payloads, sanitized reports, idempotency, row locks, and audit events.

Residual risks: rule false positives/negatives, translation nuance, provider behavior drift, compromised doctor account. Mitigations require clinician review, regression datasets, access monitoring, and periodic model evaluation.
