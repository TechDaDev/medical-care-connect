# Doctor Internal Notes

Endpoint: `GET|POST /api/messaging/{consultation_id}/internal-notes/`. Assigned approved doctor only. Patient, unrelated doctor, and non-doctor roles denied.

List is paginated (20 default, 50 maximum). Output: note ID, safe author ID/display name/role, content, and timestamps. Author email and consultation internals absent.

Creation accepts `content` and required UUID `client_request_id`. Normalized content must contain at least ten meaningful alphanumeric characters and remain within 5,000 characters. Unique author/request ID makes retries idempotent.

Creation emits sanitized audit metadata containing consultation and note identifiers only. It sends no patient notification. Patient consultation APIs never serialize internal notes. Frontend labels section private and patient-invisible.
