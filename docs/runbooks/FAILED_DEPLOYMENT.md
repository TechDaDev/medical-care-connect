# Runbook: Failed Deployment

## Symptoms

- Build failure in CI
- 5xx errors after deploy
- Health check fails after deploy
- Railway deployment shows error

## Impact

- New features/ fixes unavailable
- Existing service may be degraded

## Severity

- **High** — partial if previous version still running
- **Critical** — if both old and new versions down

## Actions

### 1. Check build logs

```bash
# Railway CLI
railway logs --deploy <deployment-id>

# GitHub Actions
# View workflow run output on GitHub
```

### 2. Identify failure

Common causes:
- Missing environment variable
- Migration conflict
- Syntax error in new code
- Dependency version mismatch

### 3. Fix forward (if quick)

If the fix is small:
1. Create fix commit
2. Push to deploy branch
3. Let CI run again

### 4. Rollback

```bash
# Git rollback
git revert HEAD
git push origin main

# Railway redeploy
railway up --detach
```

Or use Railway dashboard to redeploy previous successful deployment.

### 5. Verify rollback

```bash
curl http://<production-url>/api/health/
curl http://<production-url>/api/readiness/
```

## Validation

- Health endpoint returns 200
- Readiness endpoint returns `ready`
- Test a core flow (login, list consultations)

## Rollback

Rollback is reverting git and redeploying. No data rollback needed unless
migration caused issues — then follow [DATABASE_RESTORE.md](DATABASE_RESTORE.md).

## Related

- [SERVICE_OUTAGE.md](SERVICE_OUTAGE.md)
- [COOKIE_AUTH_INCIDENT.md](COOKIE_AUTH_INCIDENT.md)
