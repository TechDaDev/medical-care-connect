# Doctor Consultation Workspace

Doctor-safe detail: `GET /api/consultations/{id}/doctor/`. Only assigned approved doctor receives data. Unrelated assignment returns not found; pending/inactive doctor returns forbidden.

Contract includes patient clinical summary fields, complaint description, localized specialty, timestamps, server timeline, action flags and reason codes, intake/message/attachment/internal-note/record summaries, and generation time. It excludes email, phone, address, cancellation reason, staff fields, message/note bodies, attachment storage data, raw AI prompts, provider/model metadata, and hidden intake fields.

Workspace route: `/app/doctor/consultations/:consultationId`. Sections: patient summary, intake review, private notes, attachments, workflow actions, messaging link, and timeline. Actions use accessible confirmation dialogs. Disabled actions display backend reason codes. Emergency intake signal receives prominent alert.

React Query keys isolate queue, detail, intake, notes, and attachments. Successful mutation invalidates current authoritative detail and queue only. Intake answer detail loads only when doctor opens intake section.

Medical-record summary is read-only. `action_path` remains `null`; Phase B creates no unverified doctor medical-record route.
