"""Synthetic-only clinician review export and validated disposition import."""

import csv
from datetime import date
from pathlib import Path

from .registry import ALL_RULES, RULESET_VERSION

ALLOWED_DISPOSITIONS = {
    "unreviewed",
    "approved",
    "approved_with_changes",
    "rejected",
    "needs_more_evidence",
}
DECISIONS_REQUIRING_REVIEWER = {"approved", "approved_with_changes", "rejected"}
REVIEW_FIELDS = (
    "rule_id", "rule_code", "ruleset_version", "rule_version", "language",
    "severity", "pattern", "pattern_type", "positive_examples",
    "negative_examples", "negation_examples", "historical_examples",
    "family_context_examples", "ambiguity_notes", "enabled",
    "clinician_review_status", "reviewer", "reviewer_role", "review_date",
    "disposition", "review_notes",
)


class ReviewValidationError(ValueError):
    pass


def _examples(rule) -> dict[str, str]:
    if rule.language == "en":
        return {
            "positive_examples": f"Synthetic current statement containing: {rule.pattern}",
            "negative_examples": "Synthetic routine statement without this symptom.",
            "negation_examples": f"Synthetic patient says they do not have: {rule.pattern}",
            "historical_examples": f"Synthetic patient had this three years ago: {rule.pattern}",
            "family_context_examples": f"Synthetic family member has: {rule.pattern}",
        }
    if rule.language == "ar":
        return {
            "positive_examples": f"مثال اصطناعي حالي: {rule.pattern}",
            "negative_examples": "مثال اصطناعي اعتيادي بلا هذا العرض.",
            "negation_examples": f"مثال اصطناعي منفي: لا أعاني من {rule.pattern}",
            "historical_examples": f"مثال اصطناعي تاريخي قبل ثلاث سنوات: {rule.pattern}",
            "family_context_examples": f"مثال اصطناعي عن فرد من العائلة: {rule.pattern}",
        }
    return {
        "positive_examples": f"نموونەی دەستکردی ئێستا: {rule.pattern}",
        "negative_examples": "نموونەی دەستکردی ئاسایی بەبێ ئەم نیشانەیە.",
        "negation_examples": f"نموونەی دەستکردی نەرێنی: {rule.pattern} نییە",
        "historical_examples": f"نموونەی دەستکردی مێژوویی: {rule.pattern}",
        "family_context_examples": f"نموونەی دەستکرد بۆ خێزان: {rule.pattern}",
    }


def review_rows() -> list[dict[str, str]]:
    rows = []
    for rule in ALL_RULES:
        row = {
            "rule_id": rule.rule_id,
            "rule_code": rule.code,
            "ruleset_version": RULESET_VERSION,
            "rule_version": rule.version,
            "language": rule.language,
            "severity": rule.severity,
            "pattern": rule.pattern,
            "pattern_type": rule.pattern_type,
            "ambiguity_notes": "Clinician assessment required.",
            "enabled": str(rule.enabled).lower(),
            "clinician_review_status": rule.clinician_review_status,
            "reviewer": "",
            "reviewer_role": "",
            "review_date": "",
            "disposition": rule.clinician_review_status,
            "review_notes": "",
            **_examples(rule),
        }
        rows.append(row)
    return rows


def export_review_csv(path: str | Path) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = review_rows()
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def import_review_csv(path: str | Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(REVIEW_FIELDS).issubset(reader.fieldnames):
            raise ReviewValidationError("Review file is missing required columns.")
        rows = list(reader)

    rules = {rule.rule_id: rule for rule in ALL_RULES}
    seen = set()
    records = []
    for row in rows:
        rule_id = row["rule_id"]
        if rule_id in seen:
            raise ReviewValidationError(f"Duplicate rule id: {rule_id}")
        seen.add(rule_id)
        rule = rules.get(rule_id)
        if rule is None or row["rule_code"] != rule.code:
            raise ReviewValidationError(f"Unknown emergency rule: {rule_id}")
        if row["ruleset_version"] != RULESET_VERSION:
            raise ReviewValidationError("Emergency ruleset version mismatch.")
        if row["rule_version"] != rule.version:
            raise ReviewValidationError(f"Rule version mismatch: {rule_id}")
        if row["pattern"] != rule.pattern or row["pattern_type"] != rule.pattern_type:
            raise ReviewValidationError(f"Review import cannot alter pattern: {rule_id}")
        if row["enabled"].lower() != str(rule.enabled).lower():
            raise ReviewValidationError(f"Review import cannot alter runtime status: {rule_id}")
        disposition = row["disposition"].strip()
        if disposition not in ALLOWED_DISPOSITIONS:
            raise ReviewValidationError(f"Invalid disposition: {disposition}")
        reviewer = row["reviewer"].strip()
        review_date = row["review_date"].strip()
        if disposition in DECISIONS_REQUIRING_REVIEWER and not reviewer:
            raise ReviewValidationError(f"Reviewer required for {disposition}: {rule_id}")
        if disposition in DECISIONS_REQUIRING_REVIEWER and not review_date:
            raise ReviewValidationError(f"Review date required for {disposition}: {rule_id}")
        if review_date:
            try:
                date.fromisoformat(review_date)
            except ValueError as exc:
                raise ReviewValidationError(f"Invalid review date: {rule_id}") from exc
        records.append({
            "rule_id": rule.rule_id,
            "rule_code": rule.code,
            "ruleset_version": RULESET_VERSION,
            "rule_version": rule.version,
            "language": rule.language,
            "severity": rule.severity,
            "pattern": rule.pattern,
            "enabled": rule.enabled,
            "disposition": disposition,
            "reviewer": reviewer,
            "reviewer_role": row["reviewer_role"].strip(),
            "review_date": review_date,
            "review_notes": row["review_notes"].strip(),
        })
    if seen != set(rules):
        raise ReviewValidationError("Review file must contain every rule exactly once.")
    return records
