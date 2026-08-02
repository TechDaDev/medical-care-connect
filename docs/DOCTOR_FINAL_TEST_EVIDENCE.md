# Doctor Final Test Evidence

Evidence date: 2026-08-02.

| Gate | Command/scope | Result |
| --- | --- | --- |
| Fixture safety + Phase E closure | `tests.test_phase_f tests.test_doctor_phase_e` | 10 passed, 0 failed/skipped |
| Backend full | Django test suite | 443 total: 429 passed, 14 skipped, 0 failed; 397.814s |
| Frontend lint/types | ESLint and TypeScript | Passed |
| Frontend unit | Vitest full suite | 11 files, 169 passed, 0 failed/skipped |
| Frontend coverage | Vitest coverage | statements 58.88%, branches 53.19%, functions 57.80%, lines 61.34% |
| Frontend build | clean production build | Passed; 2,094 modules; no source maps |
| Playwright | desktop plus mobile full suite | 184 passed, 2 skipped, 0 failed; 7.2m |
| PostgreSQL | Doctor Phase A-E matrix | 64 passed, 0 failed/skipped; 29.518s |
| Accessibility | Axe plus AccessLint | Doctor Axe passed; AccessLint public scan 16 out-of-scope findings |
| Dependency audit | Python and npm | runtime Python clean; local pip tool 6 findings; npm 2 high from one React Router advisory |
| Migrations | dry-run/check/deploy check | no model changes; migration check passed; local placeholder-secret W009 only |
| Docker | clean backend/frontend builds and smoke | Passed after frontend IPv6 healthcheck remediation |

Backend skips: 13 PostgreSQL-only row-lock cases and one PostgreSQL-only backup test. All 13 workflow row-lock cases passed in PostgreSQL run. Playwright skips: two desktop-only mobile interaction cases; both passed in mobile project.
