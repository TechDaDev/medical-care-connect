# Privacy Workflows

## Models

### DataExportRequest

Tracks the lifecycle of a user data export.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `requested_by` | FK→User | Who initiated the request |
| `subject_user` | FK→User | Whose data is exported |
| `status` | Enum | `pending`, `processing`, `completed`, `failed`, `expired`, `deleted` |
| `requested_at` | DateTime | When created |
| `started_at` | DateTime | When processing began |
| `completed_at` | DateTime | When processing finished |
| `expires_at` | DateTime | When download link expires |
| `storage_provider` | string | Backend used for storage |
| `storage_key` | string | Key in storage backend (not exposed via API) |
| `checksum` | string | File integrity hash |
| `size_bytes` | bigint | Export file size |
| `failure_code` | string | Machine-readable failure reason |
| `created_by_staff` | bool | Whether admin initiated |

### AccountDeletionRequest

Tracks the lifecycle of an account deletion.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `subject_user` | FK→User | User to delete |
| `requested_by` | FK→User | Who requested |
| `status` | Enum | `pending`, `approved`, `rejected`, `scheduled`, `completed`, `cancelled` |
| `reason` | Text | User-provided reason |
| `requested_at` | DateTime | When created |
| `reviewed_at` | DateTime | When reviewed |
| `reviewed_by` | FK→User | Admin reviewer |
| `scheduled_for` | DateTime | When deletion will execute |
| `completed_at` | DateTime | When deletion completed |
| `rejection_reason` | Text | Why rejected |

## Export Flow

```
┌─────────┐    ┌───────────┐    ┌────────────┐    ┌───────────┐
│ PENDING │───→│ PROCESSING │───→│ COMPLETED  │───→│  EXPIRED  │
└─────────┘    └───────────┘    └────────────┘    └───────────┘
                                        │                │
                                        ↓                ↓
                                    DELETED          DELETED
```

1. **Request** — User POSTs `/api/privacy/exports/`. Status: `pending`.
2. **Process** — Background task collects data. Status: `processing`.
3. **Complete** — Zip file written to storage. Status: `completed`.
4. **Download** — User GETs download endpoint within expiry window.
5. **Expire** — After `DATA_EXPORT_EXPIRY_DAYS` (default 7). Status: `expired`.
6. **Delete** — User or admin marks export deleted. Status: `deleted`.

### What Export Includes

- User profile fields (name, email, phone)
- Patient profile data
- Consultation metadata (not clinical notes)
- Message history (you are the sender)
- Notification history
- Attachment metadata (not file contents — too large)

### What Export Excludes

- Medical records (retained for legal compliance)
- Doctor internal notes
- Attachment file contents (metadata only)
- Audit events (internal operations)
- Other users' personal data

## Account Deactivation

User deactivates own account:

```http
POST /api/privacy/account/deactivate/
Authorization: Bearer <token>
Content-Type: application/json

{"password": "current_password"}
```

- Sets `user.is_active = False`
- User cannot log in
- Data is preserved (reversible)
- Admin can reactivate via `/api/privacy/account/reactivate/`

## Account Deletion Request

### User Flow

1. User creates deletion request:
   ```http
   POST /api/privacy/deletion-requests/
   Authorization: Bearer <token>
   Content-Type: application/json
   
   {"reason": "I want to delete my account"}
   ```

2. Status: `pending`. Admin reviews.

3. User can cancel pending request:
   ```http
   POST /api/privacy/deletion-requests/{id}/cancel/
   ```

### Staff Review

Admin reviews via staff endpoints:

- `POST /api/staff/privacy/deletion-requests/{id}/approve/`
- `POST /api/staff/privacy/deletion-requests/{id}/reject/`
  - Rejection requires `rejection_reason`

### Approved Deletion

When approved, the system:
- Sets status to `scheduled` with `scheduled_for` date
- On execution, sets status to `completed`
- **Anonymization is preview-only** — current implementation
  (`PreviewOnlyAnonymizer`) reports affected records without mutation

### Anonymization Preview

What the anonymizer reports:

| Action | Records |
|--------|---------|
| Anonymize | User name, phone, patient profile, message sender |
| Delete | Notifications, data export requests |
| Retain (legal) | Consultations, audit events |
| Blocked (retention) | Medical records, attachments |

## Retention Policy

| Data Type | Retention | Notes |
|-----------|-----------|-------|
| Medical records | Indefinite | Legal/medical compliance |
| Consultations | Indefinite | Medical record reference |
| Messages | Indefinite | Care continuity |
| Attachments (deleted) | 90 days | Configurable via `ATTACHMENT_RETENTION_DAYS` |
| Audit events | Indefinite | Internal operations |
| Data exports | 7 days | Configurable via `DATA_EXPORT_EXPIRY_DAYS` |

## Endpoints Summary

### User-Facing

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/privacy/exports/` | Request data export |
| GET | `/api/privacy/exports/` | List own exports |
| GET | `/api/privacy/exports/{id}/` | Export detail |
| GET | `/api/privacy/exports/{id}/download/` | Download export file |
| DELETE | `/api/privacy/exports/{id}/` | Delete completed/expired export |
| POST | `/api/privacy/account/deactivate/` | Deactivate own account |
| POST | `/api/privacy/account/reactivate/` | Reactivate (admin only) |
| POST | `/api/privacy/deletion-requests/` | Request account deletion |
| GET | `/api/privacy/deletion-requests/` | List own deletion requests |
| GET | `/api/privacy/deletion-requests/{id}/` | Deletion request detail |
| POST | `/api/privacy/deletion-requests/{id}/cancel/` | Cancel pending request |

### Staff-Only

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/staff/privacy/deletion-requests/{id}/approve/` | Approve deletion |
| POST | `/api/staff/privacy/deletion-requests/{id}/reject/` | Reject deletion |
