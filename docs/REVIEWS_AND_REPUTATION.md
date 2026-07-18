# Reviews & Reputation — Phase 11

## Overview

Phase 11 adds a complete review, reputation, moderation, and trust workflow to MCC.
Patients rate completed consultations (1–5★), doctors respond, and staff moderate.

## Architecture

### Models (`apps/reviews/models.py`)

| Model | Description |
|-------|-------------|
| `ConsultationReview` | Patient review of a completed consultation. One-to-one with Consultation. Status: published / under_review / hidden / removed. |
| `DoctorReviewResponse` | Doctor's response to a review. One-to-one with ConsultationReview. |
| `ReviewReport` | User-submitted report on a review. Supports 6 reason categories. |

### Key Fields

- **ConsultationReview**: rating (1-5), title, body, is_anonymous, status, edit_count, last_edited_at, moderated_at, moderated_by, has_response (denormalised)
- **DoctorReviewResponse**: body (text)
- **ReviewReport**: reason (choice), description, resolved_at, resolved_by, resolution (choice)

### Endpoints

| Method | Path | Description | Permissions |
|--------|------|-------------|-------------|
| POST/GET | `/api/reviews/consultations/<uuid>/review/` | Create or get review | Patient (owner) |
| PATCH/DELETE | `.../review/edit/` | Update/delete review (72hr window) | Patient (owner) |
| GET | `/api/reviews/doctors/<uuid>/reviews/` | Paginated published reviews | Authenticated |
| GET | `/api/reviews/doctors/<uuid>/reputation/` | Aggregated reputation | Authenticated |
| POST/PATCH/DELETE | `/api/reviews/reviews/<uuid>/response/` | Doctor response | Doctor (owner) |
| POST | `/api/reviews/reviews/<uuid>/report/` | Report a review | Authenticated |
| GET | `/api/staff/reviews/` | Staff review list | Coordinator/Admin |
| PATCH | `/api/staff/reviews/<uuid>/moderate/` | Moderate a review | Coordinator/Admin |
| GET | `/api/staff/reviews/reports/` | List reports | Coordinator/Admin |
| PATCH | `/api/staff/reviews/reports/<uuid>/resolve/` | Resolve report | Coordinator/Admin |

### Notifications Added

- `REVIEW_AVAILABLE` — doctor notified of new/updated review
- `REVIEW_RESPONSE` — patient notified of doctor's response
- `MODERATION_STATE` — patient notified when review status changes
- `REPORT_RESOLUTION` — reporter notified when report is resolved

### Edit Window

Patients can edit/delete their review within **72 hours** of creation.

### Moderation States

1. **Published** — visible to all authenticated users
2. **Under Review** — flagged for staff inspection
3. **Hidden** — hidden from public but retained
4. **Removed** — deleted from public view

### Reputation Calculation

- Average rating (1.00 – 5.00)
- Rating distribution (count per star level)
- Response rate (% of reviews with doctor response)
- Recent trend (improving / declining / stable) — compares last 10 vs previous 10

## Frontend

### Patient Flow

1. After consultation is **completed**, a "Write a Review" section appears on the consultation detail page
2. Star rating (1-5), optional title, optional body, anonymous toggle
3. Review shown inline after submission
4. 72hr edit/delete window

### Doctor Flow

1. **/app/doctor/reviews** — see all reviews for the doctor's consultations
2. Reputation card with average rating, distribution bars, trend indicator
3. Respond to each review inline

### Staff Flow

1. **/app/staff/reviews** — tabbed interface (Reviews / Reports)
2. Filter reviews by status
3. Moderate reviews (publish / hide / remove) with reason
4. View and resolve reports

### Permissions

- Patients: create/update/delete own reviews
- Doctors: respond to reviews on their consultations
- Coordinators/Admins: moderate reviews, resolve reports
- All authenticated: view published reviews and reputation
