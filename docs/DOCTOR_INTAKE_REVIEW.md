# Doctor Intake Review

Endpoint: `GET /api/consultations/{id}/doctor-intake/`. Permission: assigned active approved doctor.

Contract provides session/consultation IDs, status/timestamps, question and answered counts, emergency flag, paired patient answers, allowlisted doctor-safe summary, missing-field names, and begin-review capability.

Safe summary allowlist: reported concern, symptoms, duration, severity, medications, allergies, chronic conditions, surgical history, and family history. Response excludes system messages, raw prompts, prompt templates, provider/model configuration, tokens, traces, moderation internals, and full collected-data object.

Incomplete intake returns summary state from detail; dedicated endpoint returns not found until session exists. Emergency signal never unlocks restricted doctor mutations. Begin review remains backend-authoritative.
