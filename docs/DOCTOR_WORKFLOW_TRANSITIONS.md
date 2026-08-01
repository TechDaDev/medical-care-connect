# Doctor Workflow Transitions

All doctor mutations pass through `apps.consultations.doctor_actions.perform_doctor_action`. Service checks approval, assignment, expected status/timestamp, legal transition, reason, transfer target, and completion prerequisites inside transaction with row lock.

| Action | From | To | Reason |
|---|---|---|---|
| accept | submitted | accepted | optional |
| begin_review | intake_completed | doctor_review | optional |
| begin_review / mark_awaiting_doctor | awaiting_doctor_response | under_review | optional |
| request_patient_response | doctor_review, under_review | awaiting_patient_response | required |
| require_follow_up | doctor_review, under_review | follow_up_required | required |
| require_physical_visit | doctor_review, under_review | physical_visit_required | required |
| complete | doctor_review, under_review, follow_up_required, physical_visit_required | completed | required; record required |
| transfer | any nonterminal, nonemergency state | transferred | required; eligible same-specialty target required |

`client_request_id` is unique per actor. Exact retries return current authoritative detail without new transition, notification, or audit. Reuse for different consultation/action conflicts. `expected_status` and optional `expected_updated_at` reject stale clients. Row lock serializes competing mutations on PostgreSQL.

Action events are append-only. Audit/notifications carry IDs, action, and statuses; no complaint, clinical reason text, message, note, or intake answer.
