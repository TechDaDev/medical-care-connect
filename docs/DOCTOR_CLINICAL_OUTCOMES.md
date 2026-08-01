# Doctor clinical outcomes

Consultation outcome transition requires finalized record ID, explicit matching outcome, confirmation, current consultation state/version, reason, and assigned-doctor authority.

| Action | Outcome | Consultation state |
|---|---|---|
| `complete` | `remote_care_completed` | completed |
| `require_follow_up` | `follow_up_required` | follow-up required |
| `require_physical_visit` | `physical_visit_required` | physical visit required |
| `transfer` | `transferred` | transferred and reassigned |
| `emergency_escalate` | `emergency_escalated` | emergency escalated |

Backend action policy is authoritative. Frontend sends only actions returned as available. Outcome metadata is system-owned on finalized record; it does not reopen doctor-authored content. Audit and notification text remain narrative-free.
