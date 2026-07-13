# CI/CD

## Overview

Three CI workflows run on GitHub Actions for the backend repository. Frontend
has its own CI in the frontend repository.

## Workflows

### backend-ci.yml

Triggers on PR or push to `main` affecting Python files.

**Steps:**

1. **Checkout** — `actions/checkout@v4`
2. **Python setup** — `actions/setup-python@v5`, Python 3.12, pip cache
3. **Install deps** — `pip install -r requirements.txt`
4. **Run checks:**
   - `python manage.py check` — Django system checks
   - `python manage.py makemigrations --check` — No uncommitted migrations
   - `python manage.py migrate` — Apply migrations to test DB
   - `python manage.py test` — Run full test suite
5. **Collect static** — `python manage.py collectstatic --noinput`
6. **Production check** — `python manage.py check --deploy` with production
   settings
7. **Docker build** — `docker build --no-cache -t mcc-backend:ci .`

**PostgreSQL service container:**
- Image: `postgres:16`
- Database: `mcc_test`
- Health check: `pg_isready`

**No production secrets** are used. CI uses throwaway credentials.

### e2e-ci.yml

Triggers on PR affecting `src/`, `e2e/`, `package.json`, or compose files.

**Steps:**

1. **Checkout**
2. **Python setup** — install backend deps
3. **Node setup** — `actions/setup-node@v4`, Node 22, npm cache
4. **Install frontend deps** — `npm ci`
5. **Backend migrations** — migrate on test DB
6. **Seed data** — `python manage.py seed_data`
7. **Start backend** — `python manage.py runserver &`
8. **(Playwright tests run in frontend repo)**

**PostgreSQL service container:**
- Image: `postgres:16`
- Database: `mcc_e2e`

### security-ci.yml

Triggers on every PR and push to `main`.

**Steps:**

1. **Checkout**
2. **Committed .env check** — Fail if `.env` found
3. **Private key check** — Scan for `.key`, `.pem`, `.p12` files
4. **JWT localStorage regression** — Ensure no direct localStorage token writes
5. **storage_key exposure** — Ensure no backend storage keys leak to frontend
6. **Public media routes** — Ensure `MEDIA_URL` not exposed
7. **API key patterns** — Scan for hardcoded `API_KEY` in code
8. **npm audit** — Non-blocking, frontend deps only

## What CI Verifies

| Check | Workflow | Fail on |
|-------|----------|---------|
| Django system checks | backend-ci | Warnings/errors |
| Uncommitted migrations | backend-ci | Missing migration files |
| Tests pass | backend-ci | Any test failure |
| Production settings | backend-ci | Deployment warnings |
| Docker build | backend-ci | Build failure |
| E2E tests | e2e-ci | Test failure |
| .env committed | security-ci | Tracked .env file |
| Secrets in code | security-ci | Keys, certs, tokens |
| npm vulnerabilities | security-ci | High-severity issues |

## No Production Secrets

All CI workflows use environment-specific throwaway credentials:

- `SECRET_KEY: ci-test-key-not-for-production`
- `POSTGRES_PASSWORD: mcc_test_pass` / `mcc_e2e_pass`
- `DEEPSEEK_API_KEY: ""` (AI disabled in CI)

## Local CI Simulation

```bash
# Run the same checks locally
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test
python manage.py collectstatic --noinput
python manage.py check --deploy --settings=config.settings.production
```
