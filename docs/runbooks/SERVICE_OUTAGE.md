# Runbook: Service Outage

## Symptoms

- Health endpoint returns non-200
- Readiness endpoint returns 503
- Users report site unreachable
- Monitoring alert fired

## Impact

- All users unable to access service
- Patients cannot create consultations or use AI intake
- Doctors cannot review or respond to consultations

## Severity

- **Critical**

## Actions

### 1. Check health endpoint

```bash
curl -f http://localhost:8000/api/health/
```

### 2. Check readiness endpoint

```bash
curl http://localhost:8000/api/readiness/
```

### 3. Check application logs

```bash
# Recent errors
docker compose logs --tail=100 backend | grep -i error

# Security events
docker compose logs --tail=50 backend | grep mcc.security

# Slow requests
docker compose logs --tail=50 backend | grep request.slow
```

### 4. Check database connectivity

```bash
docker compose exec db pg_isready
```

### 5. Check database connection count

```bash
docker compose exec db psql -U mcc_user -c "SELECT count(*) FROM pg_stat_activity;"
```

### 6. Restart service

```bash
docker compose restart backend
```

### 7. Check after restart

```bash
sleep 5
curl http://localhost:8000/api/health/
curl http://localhost:8000/api/readiness/
```

## Escalation

If service does not recover after restart:

1. Check disk space:
   ```bash
   docker compose exec db df -h
   ```

2. Check DB logs:
   ```bash
   docker compose logs --tail=100 db
   ```

3. Restart entire stack:
   ```bash
   docker compose down
   docker compose up -d
   ```

4. If DB corrupt, follow [DATABASE_RESTORE.md](DATABASE_RESTORE.md)

5. Contact infrastructure team if Railway-side issue suspected

## Related

- [FAILED_DEPLOYMENT.md](FAILED_DEPLOYMENT.md)
- [DATABASE_RESTORE.md](DATABASE_RESTORE.md)
