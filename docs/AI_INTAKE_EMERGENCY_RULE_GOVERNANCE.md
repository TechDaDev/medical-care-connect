# AI Intake Emergency Rule Governance

Rules live in `apps/ai_intake/emergency_rules/`, split by EN, AR, and CKB. Each rule records stable code, language, severity, pattern type, enabled state, version, suppression policy, and clinician-review status. Current ruleset: `mcc-emergency-rules-v1`; status: unreviewed.

Normalization uses Unicode NFKC, case folding, Arabic-script variant normalization, diacritic/tatweel removal, punctuation removal, and whitespace collapse. Context suppression covers bounded negation, family, historical, and hypothetical phrases. Self-harm rules are not suppressible. Mixed-language input scans preferred language first, then remaining registries.

Change process: add synthetic positive/negative/near-miss cases; security review; clinician review; version bump; staged release; monitor false-positive/false-negative reports without storing patient narratives in evaluation reports.
