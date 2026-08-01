# Doctor Phase B Acceptance

Acceptance requires green Django system/migration checks, full backend suite, PostgreSQL concurrency suite, frontend lint/typecheck/unit/coverage/build, Playwright doctor flow with axe, dependency audits, and no-cache Docker builds.

Security gates: assignment isolation; approval enforcement; no queue narrative; safe detail/intake allowlists; stale conflict; row locking; idempotent side effects; patient-invisible internal notes; quarantined/rejected attachment denial; private/no-store downloads; no storage path; no medical-record dead route.

Performance gates: queue aggregates and eager loads all row dependencies; detail eager loads summaries; intake prefetches messages; notes and attachments paginate and eager load author/participant data. Query-count regression should remain bounded independent of page rows.

Locales: English, Arabic, Central Kurdish. Queue tabs/filters, workspace actions/dialogs, warning text, private-note label, and states use locale keys. RTL comes from application locale provider.

Accessibility: semantic table/cards, labeled filters, status text plus icons, semantic timeline list, keyboard-accessible actions, focus-trapped dialogs, error alerts, and responsive queue/workspace.

Deferred: doctor medical-record editor/list, doctor message overview, doctor-specific notification redesign, full review management, privacy workflow, appointments, payments, prescriptions, and video. These belong to Doctor Phase C–D.
