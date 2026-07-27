# Operations Runbook

## Endpoints

- `/api/health/`: process alive; no dependency query.
- `/api/readiness/`: required database and attachment storage; ClamAV only when configured as required. Returns 503 for required dependency loss.
- `/api/staff/operations/status/`: administrator-safe diagnostic summary.
- `/api/staff/operations/metrics/`: bounded aggregate counts.

Operations status exposes version/release/short commit, environment, database/storage/scanner state, optional AI state, error monitor name, migration name, retention count, total in-app notifications, backup-storage status, and real background-task configuration state. Scanner check timestamp remains null because no persistent check record exists.

No endpoint exposes hosts, credentials, keys, private URLs, storage roots, stack traces, shell execution, SQL, restarts, deployments, or unrestricted deletion.

## Triage

1. Health non-200: process/startup problem.
2. Health 200 and readiness 503: inspect database, storage, then required scanner.
3. Readiness 200 and Operations degraded: inspect optional/operational component shown.
4. Confirm PostgreSQL with `docker compose ps`.
5. Run `manage.py check --database default` and migration checks.
6. Use dry-run maintenance commands first. Preserve request ID and audit event.

Railway deploys from GitHub. Do not trigger manual deployment. Verify intended commit, deployment success, health/readiness, and read-only routes after automatic deployment.
