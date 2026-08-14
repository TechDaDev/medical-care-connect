# AI Intake Doctor Presentation

Doctor route: `/app/doctor/consultations/:consultationId/intake`. API: `GET /api/consultations/:id/doctor-intake/`.

Contract exposes assigned patient identity, specialty, consultation/session state, patient-confirmed structured fields, per-field status/source/evidence IDs, safe patient/assistant transcript, gaps, emergency state, prompt/schema versions, and exact medical-record action. It never exposes provider credentials, hidden prompts, raw provider payloads, chain-of-thought, staff notes, or unrelated messages.

UI labels content AI-assisted and not clinically verified. Emergency block states system did not contact emergency services. Doctor must review evidence before clinical action.
