# Doctor Final Handoff

## Scope

Doctor Phases A-D: access and availability; consultation queue/workspace; medical records/outcomes; messages overview, notifications, reviews, profile, and privacy. Phase E adds acceptance evidence and only defects required to close this scope.

## Local acceptance

1. Use localhost-only database and services.
2. Set `E2E_LOCAL_ALLOWED=true`, unique `E2E_RUN_ID`, and synthetic test password.
3. Seed with `python manage.py seed_e2e_data --run-id <id>`.
4. Run backend, frontend, PostgreSQL, and Playwright evidence listed in `DOCTOR_FINAL_TEST_EVIDENCE.md`.
5. Clean with `python manage.py cleanup_e2e_data --run-id <id>` and verify zero run-scoped rows/storage objects.

Seed and cleanup refuse non-local execution, non-synthetic run IDs, non-debug mode, or missing explicit local opt-in.

## Release decision

Use `COMPLETE` only when tests, migrations, Docker, pushed commits, observed Railway deployment, production smoke, and cleanup all pass. Otherwise use `PARTIAL` and name each missing gate.

Current closure: local code, tests, PostgreSQL, browser, migrations, dependency review, Docker, synthetic cleanup, Git pushes, Railway automatic deployments, and backend production smoke passed. Frontend production smoke remains unverified because no public hostname was available; release decision is `PARTIAL`.

Medical-record amendment support remains intentionally absent. Finalized records are immutable through normal PATCH; UI exposes no false amendment action.

Legacy compatibility remains intentionally available through `DoctorProfileDetailSerializer`, marked deprecated in favor of `DoctorOwnProfileReadSerializer`. Graph zero-degree results otherwise classify as test discovery, Django migration discovery, React lazy-route modules, barrel/API-object usage, and translation-key lookups—not proven dead code.

`docs/project-skills.md` is explicitly excluded from Phase E staging and commits. It remains untouched and untracked.
