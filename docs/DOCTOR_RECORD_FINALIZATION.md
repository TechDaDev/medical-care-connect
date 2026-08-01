# Doctor record finalization

Finalization is doctor-authoritative and permanent in Phase C. Amendment workflow is deferred to Doctor Phase D.

Required policy:

- clinical summary or assessment;
- patient instructions;
- at least one recommendation, treatment plan, follow-up plan, or physical-visit reason;
- non-terminal consultation;
- current assigned approved active doctor;
- matching version and explicit confirmation.

Service locks consultation then record, preventing incompatible finalization/outcome races. Success increments version, records finalizer/time, emits one sanitized audit event, and sends one generic patient notification. Same idempotency request returns same result. New request against finalized record fails.

Finalized fields cannot be edited. Patient endpoints expose finalized records only through safe serializers. Print view uses finalized safe detail and hides interactive, AI, audit, provenance, and private-note sections.
