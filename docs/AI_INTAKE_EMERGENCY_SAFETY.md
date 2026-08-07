# AI Intake Emergency Safety

Emergency handling is deterministic and never depends on the LLM.

## Deterministic screening

`screen_patient_input` (`apps/ai_intake/services/emergency.py`) is a keyword
matcher with negation and family-history suppression windows. It supports
English, Arabic, and Kurdish Sorani phrases. It runs for every patient message:

- before any normal-flow persistence;
- before any DeepSeek call.

When a deterministic emergency is detected:

- the session stops normal questioning and enters `emergency_stopped`;
- the consultation transitions once to `emergency_escalated`;
- one doctor/staff notification is sent; one audit event is recorded;
- prior collected information is preserved;
- the patient receives localized emergency guidance;
- DeepSeek is not called;
- the system never claims emergency services were contacted;
- normal completion/submission is prevented.

## Emergency levels

- `emergency` — life-threatening signals (chest pain, breathing failure, major
  bleeding, stroke-like, anaphylaxis, self-harm, loss of consciousness).
- `urgent` — concerning signals that warrant clinician review (breathing
  difficulty, moderate bleeding, anaphylaxis warning).
- `warning` — reserved.

## AI escalation

The provider's `emergency_signal` may only increase caution (`urgent`/
`emergency`). It can never reduce or clear a deterministic emergency result.
After a deterministic stop, normal answers are rejected (409), so the model
cannot downgrade the state.

## Limitations (documented)

- This is a keyword matcher, not a clinical rule engine. No reliability or
  certification claim is made.
- Negation/family-history windows reduce obvious false positives but cannot
  guarantee accuracy.
- Arabic/Kurdish negation is intentionally conservative: any localized match
  escalates.
- Self-harm signals are never suppressed by negation or family history.
- Clinician-reviewed rule sets should replace/augment this matcher when they
  become available.

See `docs/adr/0002-ai-receptionist-authority-boundary.md`.
