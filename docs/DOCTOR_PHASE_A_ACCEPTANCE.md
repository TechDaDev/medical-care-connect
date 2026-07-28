# Doctor Phase A acceptance

Implemented:

- server-authoritative access state and dedicated SPA state routes;
- accessible loading/error/retry gates;
- bounded rich dashboard and server-authored attention;
- localized consultation states and locale-aware dates;
- doctor navigation link for weekly availability;
- recurring-slot create, edit, delete, overlap protection, stale-write control,
  row locking, ownership protection, and audit;
- semantic accepting-status switches with authoritative cache refresh;
- English, Arabic, and Central Kurdish Phase A strings and RTL;
- backend, frontend, Playwright, accessibility, security, and query regressions.

Deferred:

- doctor message overview;
- doctor medical-record list/editor;
- doctor notification redesign;
- full doctor reviews redesign;
- doctor privacy redesign.

Known medical-record route defect is closed safely for Phase A: doctor
consultation UI no longer links consultation ID as medical-record ID. No doctor
record link returns until backend supplies authoritative record ID and valid
doctor route.

Notifications remain in-app only. Availability remains weekly availability, not
appointment scheduling. Acceptance uses synthetic local accounts and data only;
production mutation is prohibited.
