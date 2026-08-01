# Doctor Phase C security review

Threats addressed:

- IDOR: all doctor queries scope through current assigned doctor; patient queries scope through patient and finalized status.
- Mass assignment: nested doctor-authored allowlist rejects unknown keys.
- Lost updates: row locks plus `expected_version`; stale writes return conflict.
- Duplicate side effects: per-actor client request ledger and request fingerprint.
- Finalization bypass: Phase C records reject legacy PATCH and patient confirmation.
- Unsafe inference: intake provenance remains separate; AI section is unavailable and never auto-applied.
- Privacy leakage: narrative-free lists, patient allowlist, generic notifications, sanitized audits.
- Transfer races: consultation and record mutate in one transaction; previous doctor loses access.

Residuals: amendments/revisions, AI suggestion acceptance history, structured coding, and formal export/PDF are deferred. Legacy unclaimed records retain old confirmation behavior until claimed through doctor command flow. No complete WCAG certification claimed.
