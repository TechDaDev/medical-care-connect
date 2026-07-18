# API Contracts

Documented actual response shapes for every frontend-facing endpoint.

---

## Authentication

### POST /api/auth/login/

**Request:**
```json
{"email": "user@example.com", "password": "..."}
```

**Response 200:**
```json
{
  "refresh": "jwt_refresh_token",
  "access": "jwt_access_token",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "first_name": "...",
    "last_name": "...",
    "full_name": "...",
    "phone_number": "...",
    "role": "patient|doctor|coordinator|administrator",
    "is_active": true,
    "is_staff": false,
    "date_joined": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z"
  }
}
```

### POST /api/auth/register/patient/

**Request:**
```json
{"email": "...", "password": "...", "password_confirm": "...", "first_name": "...", "last_name": "..."}
```

**Response 201:** Same shape as login.

### POST /api/auth/token/refresh/

**Request:** `{"refresh": "jwt_refresh_token"}`

**Response 200:** `{"access": "new_access_token"}`

### POST /api/auth/logout/

**Request:** `{"refresh": "jwt_refresh_token"}`

**Response 200:** `{"detail": "Logout successful."}`

---

## Current User

### GET /api/accounts/me/

**Response 200:**
```json
{
  "id": "uuid",
  "email": "...",
  "first_name": "...",
  "last_name": "...",
  "full_name": "...",
  "phone_number": "...",
  "role": "patient|doctor|coordinator|administrator",
  "is_active": true,
  "is_staff": false,
  "date_joined": "...",
  "updated_at": "..."
}
```

### PATCH /api/accounts/me/

Editable: `first_name`, `last_name`, `phone_number`.

---

## Patient Profile

### GET /api/patients/me/

**Response 200:**
```json
{
  "id": "uuid",
  "email": "...",
  "first_name": "...",
  "last_name": "...",
  "full_name": "...",
  "phone_number": "...",
  "date_of_birth": null,
  "gender": "male|female|not_specified",
  "preferred_language": "en|ar",
  "address": "...",
  "emergency_contact_name": "...",
  "emergency_contact_phone": "...",
  "blood_type": null,
  "notes": "",
  "created_at": "...",
  "updated_at": "..."
}
```

### PATCH /api/patients/me/

Editable: `date_of_birth`, `gender`, `preferred_language`, `address`, `emergency_contact_name`, `emergency_contact_phone`, `blood_type`, `notes`.

---

## Patient Dashboard

### GET /api/patients/me/dashboard/

**Response 200:**
```json
{
  "consultations": {
    "total": 0,
    "active": 0,
    "awaiting_patient": 0,
    "awaiting_doctor": 0,
    "completed": 0
  },
  "unread_messages": 0,
  "unread_notifications": 0,
  "recent_consultations": [
    {
      "id": "uuid",
      "status": "submitted",
      "doctor_name": "...",
      "specialty_name": "...",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

---

## Doctor Profile

### GET /api/doctors/me/

**Response 200:**
```json
{
  "id": "uuid",
  "email": "...",
  "first_name": "...",
  "last_name": "...",
  "full_name": "...",
  "phone_number": "...",
  "specialty": "uuid",
  "specialty_name": "...",
  "professional_title": "...",
  "license_number": "...",
  "qualifications": "...",
  "biography": "...",
  "years_of_experience": 0,
  "consultation_fee": "0.00",
  "languages": ["English", "Arabic"],
  "is_approved": true,
  "is_accepting_consultations": true,
  "estimated_response_minutes": 30,
  "created_at": "...",
  "updated_at": "..."
}
```

### PATCH /api/doctors/me/

Editable: `specialty`, `professional_title`, `license_number`, `qualifications`, `biography`, `years_of_experience`, `consultation_fee`, `languages`, `estimated_response_minutes`.

Read-only: `id`, `user`, `is_approved`, `created_at`, `updated_at`.

---

## Doctor Dashboard

### GET /api/doctors/me/dashboard/

**Response 200:**
```json
{
  "consultations": {
    "total_active": 0,
    "submitted": 0,
    "accepted": 0,
    "intake_completed": 0,
    "doctor_review": 0,
    "awaiting_patient": 0,
    "awaiting_doctor": 0
  },
  "unread_messages": 0,
  "unread_notifications": 0,
  "profile": {
    "is_approved": true,
    "is_accepting_consultations": true
  }
}
```

---

## Public Doctor Directory

### GET /api/doctors/?page=1&page_size=20

Supports `page` and `page_size` query params. Without page, returns plain array.

**Paginated Response:**
```json
{
  "count": 4,
  "next": "http://.../?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "full_name": "Dr. Name",
      "specialty": "uuid",
      "specialty_name": "...",
      "professional_title": "...",
      "qualifications": "...",
      "biography": "...",
      "years_of_experience": 15,
      "consultation_fee": "150.00",
      "languages": ["English"],
      "is_accepting_consultations": true,
      "estimated_response_minutes": 30
    }
  ]
}
```

### GET /api/doctors/<uuid>/

Detail response adds `created_at`.

---

## Specialties

### GET /api/specialties/

**Response 200:** Array of `{id, name, slug, description, is_active, display_order, created_at, updated_at}`.

---

## Consultations

### GET /api/consultations/

Role-scoped list. Returns array.

### POST /api/consultations/

**Request:** `{"doctor": "uuid", "specialty": "uuid", "priority": "medium", "description": "..."}`

### GET /api/consultations/<uuid>/

**Response includes `actions` flags:**
```json
{
  "actions": {
    "can_accept": false,
    "can_cancel": true,
    "can_message": true,
    "can_start_intake": false,
    "can_view_record": true,
    "can_add_internal_note": false,
    "can_transfer": false,
    "can_change_priority": false
  },
  "has_intake_session": false,
  "has_medical_record": false
}
```

---

## Staff Endpoints

All staff endpoints require coordinator or administrator role.

### GET /api/staff/dashboard/

See section 7 in spec.

### GET /api/staff/consultations/?status=&priority=&specialty=&doctor=&patient=&search=

Paginated.

### POST /api/staff/consultations/<uuid>/transfer/

**Request:** `{"doctor_id": "uuid", "reason": "text"}`

### PATCH /api/staff/consultations/<uuid>/priority/

**Request:** `{"priority": "routine|urgent|emergency"}`

### GET /api/staff/doctors/workload/

---

## Error Format

All errors return:
```json
{
  "detail": "Readable message",
  "code": "validation_error|authentication_failed|permission_denied|not_found|internal_error",
  "fields": {}
}
```

---

## Attachments

All attachment endpoints require authentication and consultation participation
(patient, assigned doctor, or staff).

### POST /api/attachments/upload/?consultation_id=UUID

**Request:** Multipart form — `file`, `category`, `description` (optional).

**Response 201:**
```json
{
  "id": "uuid",
  "category": "medical_report",
  "description": "...",
  "filename": "report.pdf",
  "size": 12345,
  "mime_type": "application/pdf",
  "sha256": "hex-digest",
  "status": "available",
  "scan_status": "not_required",
  "uploaded_by": {"id": "uuid", "full_name": "..."},
  "created_at": "2026-01-01T00:00:00Z",
  "actions": {
    "can_download": true,
    "can_delete": true,
    "can_restore": false
  }
}
```

### GET /api/attachments/?consultation_id=UUID

**Response 200:** Paginated list of attachment objects (same shape as upload
response, without `sha256`).

### GET /api/attachments/{id}/

**Response 200:** Single attachment object (same shape, no `sha256`).

### GET /api/attachments/{id}/download/

**Response 200:** Binary stream with `Content-Disposition: attachment`.

**Errors:** 403 if user not participant; 404 if deleted; 403 if quarantined.

### DELETE /api/attachments/{id}/

**Response 204:** Soft-deleted.

### POST /api/attachments/{id}/restore/

**Response 200:** Reverses soft-delete. Staff only.

### Category Values

`medical_report`, `laboratory_result`, `medical_image`, `referral`,
`identity_document`, `consent_document`, `other`

### Attachment Status Values

`pending`, `available`, `quarantined`, `rejected`, `deleted`

### Scan Status Values

`not_required`, `pending`, `clean`, `suspicious`, `infected`, `failed`

---

## Reviews (Phase 11)

### POST /api/reviews/consultations/{id}/review/

Create a review for a completed consultation.

**Request:**
```json
{
  "rating": 5,
  "title": "Great doctor",
  "body": "Very thorough and professional.",
  "is_anonymous": false
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "consultation": "uuid",
  "reviewer": "uuid",
  "reviewer_name": "Test Patient",
  "doctor_id": "uuid",
  "doctor_name": "Test Doctor",
  "rating": 5,
  "title": "Great doctor",
  "body": "Very thorough and professional.",
  "is_anonymous": false,
  "status": "published",
  "consultation_status": "completed",
  "has_response": false,
  "response": null,
  "report_count": 0,
  "edit_count": 0,
  "last_edited_at": null,
  "moderated_at": null,
  "moderation_reason": "",
  "created_at": "2026-07-18T00:00:00Z",
  "updated_at": "2026-07-18T00:00:00Z"
}
```

**Error 400:** Consultation not completed  
**Error 403:** Not patient's consultation  
**Error 409:** Review already exists

### GET /api/reviews/consultations/{id}/review/

Get existing review for consultation.

**Response 200:** Same shape as POST 201.  
**Response 404:** No review found.

### PATCH /api/reviews/consultations/{id}/review/edit/

Update review (within 72hr window).

**Request:** Any subset of `{ "rating", "title", "body", "is_anonymous" }`.

**Response 200:** Updated review.

### DELETE /api/reviews/consultations/{id}/review/edit/

Delete review (within 72hr window).

**Response 204:** No content.

### GET /api/reviews/doctors/{id}/reviews/

Paginated published reviews for a doctor.

**Response 200:**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "reviewer_name": "Anonymous",
      "doctor_name": "Dr. Test",
      "rating": 5,
      "title": "Excellent",
      "body": "...",
      "status": "published",
      "has_response": true,
      "response": { "id": "uuid", "review": "uuid", "doctor": "uuid", "body": "Thank you!", "created_at": "...", "updated_at": "..." },
      "report_count": 0,
      "is_anonymous": false,
      "created_at": "..."
    }
  ]
}
```

### GET /api/reviews/doctors/{id}/reputation/

Aggregated reputation.

**Response 200:**
```json
{
  "doctor_id": "uuid",
  "doctor_name": "Dr. Test",
  "average_rating": 4.5,
  "total_reviews": 12,
  "rating_distribution": { "1": 0, "2": 1, "3": 2, "4": 4, "5": 5 },
  "response_rate": 75.0,
  "recent_ratings_trend": "stable"
}
```

### POST /api/reviews/reviews/{id}/response/

Doctor responds to a review.

**Request:** `{ "body": "Thank you for your feedback!" }`  
**Response 201:** DoctorReviewResponse shape.

### PATCH /api/reviews/reviews/{id}/response/

Update doctor's response.

### DELETE /api/reviews/reviews/{id}/response/

Delete doctor's response. **Response 204.**

### POST /api/reviews/reviews/{id}/report/

Report a review.

**Request:**
```json
{
  "reason": "inappropriate|spam|fake|conflict_of_interest|privacy_violation|other",
  "description": "Optional details"
}
```

**Response 201:** ReviewReport shape.  
**Error 409:** Duplicate open report.

### GET /api/staff/reviews/?status=published&rating=5

Staff list of all reviews. Supports `status` and `rating` query params.

**Response 200:** Paginated reviews (same shape as doctor reviews).

### PATCH /api/staff/reviews/{id}/moderate/

Staff moderation action.

**Request:**
```json
{
  "status": "hidden|published|removed",
  "moderation_reason": "Optional reason"
}
```

**Response 200:** Updated review.

### GET /api/staff/reviews/reports/?resolved=false

Staff report list. Supports `resolved=true|false` query param.

**Response 200:** Paginated ReviewReport list.

### PATCH /api/staff/reviews/reports/{id}/resolve/

Resolve a report.

**Request:**
```json
{
  "resolution": "dismissed|content_hidden|content_removed|reviewer_warned|reviewer_suspended",
  "resolution_notes": "Optional notes"
}
```

**Response 200:** Updated ReviewReport.
# Doctor registration

`POST /api/auth/register/doctor/` accepts account fields plus `specialty`, `medical_license_number`, `years_of_experience`, `workplace_name`, `professional_bio`, and `languages`. It returns only safe user identity fields, pending application status, profile ID, and pending-approval next path. It never returns license numbers, passwords, or staff metadata.

