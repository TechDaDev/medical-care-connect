# Administrator API Reference

All paths are below `/api/staff/`. Collection responses are paginated unless noted.

| Method | Path | Roles | Purpose |
|---|---|---|---|
| GET | `dashboard/` | coordinator, administrator | Aggregate staff counts |
| GET | `consultations/` | coordinator, administrator | Staff consultation queue |
| POST | `consultations/{id}/transfer/` | coordinator, administrator | Bounded transfer |
| POST | `consultations/{id}/priority/` | coordinator, administrator | Priority change |
| GET | `doctors/workload/` | coordinator, administrator | Workload counts |
| GET | `doctors/applications/` | coordinator, administrator | Application list |
| GET | `doctors/applications/{id}/` | coordinator, administrator | Safe application detail |
| POST | `doctors/applications/{id}/review/` | coordinator, administrator | State transition |
| GET | `doctors/applications/{id}/license/` | authorized staff | Protected license bytes |
| GET | `users/`, `users/{id}/` | administrator | User list/detail |
| POST | `users/{id}/status/` | administrator | Activate/deactivate |
| POST | `users/{id}/revoke-sessions/` | administrator | Revoke refresh capability |
| POST | `users/{id}/role/` | administrator | Role change |
| GET/POST | `privacy/deletion-requests/*` | administrator | Review deletion requests |
| GET | `audit-events/`, `audit-events/{id}/` | administrator | Sanitized audit viewer |
| GET | `audit-events/export.csv` | administrator | Bounded, formula-safe CSV |
| GET/POST/PATCH | `specialties/*` | administrator | Create/edit/reorder/activate/deactivate |
| GET/POST | `attachments/*` | administrator | Safe detail and bounded quarantine actions |
| GET | `operations/status/` | administrator | Safe diagnostics |
| GET | `operations/metrics/` | administrator | Aggregate metrics |

Mutation bodies use documented action, reason, and expected-state fields. Never send model dictionaries or storage locators.
