# AI Intake Emergency Rule Clinician Review

Status: `UNREVIEWED`. Ruleset: `mcc-emergency-rules-v1`. This package supports review; it does not establish clinical validation.

Generate worksheet:

```bash
python manage.py export_emergency_rules_for_review --output /tmp/mcc-emergency-rule-review.csv
```

Qualified clinician reviews every row independently: language/dialect, intended symptom concept, severity, positive/negative examples, negation, historical context, family context, ambiguity, false-positive risk, missing critical expressions, and operational disposition.

Allowed dispositions: `unreviewed`, `approved`, `approved_with_changes`, `rejected`, `needs_more_evidence`. `clinically_validated` is not allowed. Approved, approved-with-changes, and rejected rows require reviewer and ISO review date.

Validate completed worksheet without changing patterns or runtime enablement:

```bash
python manage.py import_emergency_rule_review \
  --file /tmp/mcc-emergency-rule-review.csv \
  --output /tmp/mcc-emergency-rule-review-validated.json
```

`approved_with_changes` records recommendation only. Developer changes rule, increments ruleset version, adds regressions, and returns new version for clinician review. Approval never carries automatically to materially changed rules.

Only synthetic examples allowed. No patient names, consultation IDs, record IDs, or real intake text.
