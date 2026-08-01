# Doctor medical-record data ownership

| Data class | Source | Doctor may edit | Patient projection | Audit/log content |
|---|---|---:|---:|---|
| Patient-reported concern and structured history | consultation/intake | No | Yes after finalization | IDs and source labels only |
| Intake extraction | intake service | No | Selected clinical fields after finalization | IDs and provenance labels only |
| AI suggestion | future suggestion service | Never auto-authoritative | No | No prompt, response, or confidence |
| Doctor-authored clinical fields | assigned approved doctor | Draft only | Explicit allowlist after finalization | Changed field names only |
| Private doctor notes | assigned approved doctor | Draft only | Never | Field name only |
| Version, provenance, idempotency, audit metadata | system | No | Never | Operational metadata only |

Provenance values are machine-readable source labels. Intake values seed patient-reported storage, not doctor-authored fields. Empty or generated prose is never presented as doctor-authored clinical judgment.
