# AI Intake Phase A Security

Security review notes for the AI intake Phase A implementation.

## Attack paths closed

1. Patient accesses another intake — ownership filter on every endpoint (404).
2. Doctor accesses unrelated intake — assigned-doctor filter (404).
3. Patient forces ready-for-review — backend completeness gate; provider
   `propose_review` is advisory.
4. Patient forces submitted state — confirmed-state + completeness + optimistic
   concurrency gates.
5. Patient bypasses emergency stop — deterministic screening before any
   persistence/provider call; terminal state rejects further answers.
6. Duplicate answer triggers duplicate provider calls — idempotency ledger and
   `client_request_id`; concurrent turns serialized by session row lock.
7. Provider error leaks API details — generic localized patient message; safe
   codes only; raw exception text never returned.
8. Prompt injection reveals system prompt — prompt architecture treats patient
   text as data; semantic validation blocks disclosure wording; tests cover the
   injection corpus.
9. AI invents medication/allergy/history — evidence grounding guard rejects
   ungrounded explicit/inferred extractions.
10. AI writes diagnosis into record — no diagnosis field exists in the schema;
    semantic validation blocks diagnostic patient-facing content; draft
    separation leaves doctor-authored fields empty.
11. Patient edits doctor-authored fields — corrections are allowlisted to
    intake fields only.
12. Draft appears as finalized patient record — draft status is `draft`, not
    `finalized`; patient projection exposes finalized records only.
13. Audit logs contain intake text — audit events record field names and codes,
    never content.
14. Notifications contain symptoms — notification bodies are fixed generic
    strings.
15. Unbounded input causes cost exhaustion — answer length, history, prompt,
    output, session-token, and question budgets are bounded.
16. Concurrent answers corrupt ordering — transactional sequence allocation
    under the session row lock; PostgreSQL concurrency tests cover this.
17. Live provider called by E2E — E2E uses deterministic local provider mocks.
18. Production intake mutated by tests — tests use isolated synthetic data and
    dedicated test databases.

## Patterns audited

- No raw exception responses.
- No full prompt logging; patient messages are not logged by audit/request
  loggers (see `apps/core/logging.py`).
- No `fields = "__all__"` on intake serializers (explicit fields).
- No unrestricted JSON writes — field metadata writes are allowlisted.
- No direct session/consultation status writes outside services (state machine
  centralizes transitions).
- No record fields populated from AI outside the approved draft map.
- Provider output is schema- and semantically validated before storage.
- Ownership filters present on all patient/doctor intake endpoints.
- Bounded history and answer length.
- No synchronous unbounded retry loops (bounded backoff).
- No API key exposure (settings only; `.env` not committed; `.env.example`
  documents keys without values).

## Audit policy

Audited events: session started, answer accepted, emergency escalated, review
generated, patient correction, confirmation, submission, provider failure code,
draft generated. Metadata may include actor id, session/consultation id,
action, field names changed, state transition, safe error code, provider/model
id, prompt/schema version, token totals, emergency level code, client request
id. Content (messages, symptoms, medications, allergies, summaries, prompts,
responses, diagnosis, treatment) is never included.

## Observability

Safe metrics/counters where supported: sessions started/confirmed/submitted/
abandoned, emergency stops, provider failures by safe code, malformed
responses, semantic-validation failures, average questions, token totals,
latency, retry counts, completion rate. These are operational metrics, not
clinical-quality metrics. Correlation ids are used; patient text never enters
metrics/logs.
