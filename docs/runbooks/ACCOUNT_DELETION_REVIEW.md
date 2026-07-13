# Runbook: Account Deletion Review

## Symptoms

- New `AccountDeletionRequest` in `pending` status
- Admin notification of deletion request
- User support ticket about account deletion

## Impact

- User account preserved until decision made
- User may be unable to perform actions pending review
- User may contact support about request status

## Severity

- **Normal** — requires human review within SLA (e.g., 7 days)

## Actions

### 1. Review deletion request

```http
GET /api/staff/privacy/deletion-requests/{id}/
```

Check:
- User's role and account history
- Reason provided for deletion
- Any pending consultations or obligations
- Legal retention requirements

### 2. Approve or reject

**Approve:**
```http
POST /api/staff/privacy/deletion-requests/{id}/approve/
```

- Sets status to `scheduled`
- Deletion executes on `scheduled_for` date
- Anonymization is preview-only currently (see note)

**Reject:**
```http
POST /api/staff/privacy/deletion-requests/{id}/reject/
Content-Type: application/json

{"rejection_reason": "Cannot delete: pending consultation OBL-2026-001"}
```

- Sets status to `rejected`
- User can see the rejection reason
- User can re-request later

### 3. Follow up

If approved:
- Inform user of expected deletion timeline
- Note: current anonymizer is `PreviewOnlyAnonymizer` — data is reported but
  not destructively mutated

If rejected:
- Inform user of reason
- Help resolve any blockers (e.g., complete consultation first)

## Privacy Precautions

- Do not share deletion request details with unauthorized parties
- Verify the requestor's identity before discussing request status
- Approved deletions should be logged as security event
- Medical records are retained per legal requirements regardless of deletion

## Legal Retention Requirements

The following data may not be deleted even after account deletion approval:

| Data Type | Reason |
|-----------|--------|
| Medical records | Medical record retention laws |
| Consultation history | Care continuity requirements |
| Audit logs | Operations and security auditing |

These are reported as `blocked_by_retention` by the anonymizer.

## Related

- [PRIVACY_WORKFLOWS.md](../PRIVACY_WORKFLOWS.md)
- [SECRET_ROTATION.md](SECRET_ROTATION.md) (if account security concern)
