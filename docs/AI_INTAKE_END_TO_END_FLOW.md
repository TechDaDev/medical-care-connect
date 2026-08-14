# AI Intake End-to-End Flow

1. Patient starts or resumes one intake session.
2. Backend screens every patient message with deterministic emergency rules before model use.
3. Backend validates provider JSON, schema, semantics, supported fields, completeness, and state transition.
4. Patient reviews, corrects, confirms, then submits idempotently.
5. Submission enters doctor-review workflow and creates safe notifications/audit events.
6. Assigned approved doctor reads safe projection and exact evidence.
7. Medical-record draft remains separate; AI data never becomes doctor-authored content automatically.

Authority: backend state machine, emergency detector, completeness service, assignment/doctor-access policy. Model output is advisory input only.
