# Doctor Final Performance Review

Doctor list endpoints use pagination, selected/prefetched relations, and measured query ceilings in Phase A-D backend suites. Fresh full and PostgreSQL suites passed against expanded synthetic lifecycle data.

| Surface | Measured count/ceiling |
| --- | --- |
| Access state | at most 1 |
| Dashboard | exactly 10; unchanged after 12 additional consultations |
| Consultation queue | at most 3 |
| Consultation workspace | at most 2 |
| Medical-record list | at most 4 |
| Medical-record detail | at most 3 |
| Message threads | exactly 2 |
| Profile | exactly 1 |
| Notifications | exactly 3 |
| Reviews | exactly 3 |
| Privacy overview/exports/deletion | exactly 2 each |

Frontend production build uses route-level lazy loading. Final evidence records bundle output, source-map exposure check, asset caching, Docker response behavior, and route smoke results.

Frontend production build transformed 2,094 modules. Largest emitted chunks: i18n 306.10 kB (67.00 kB gzip), main 221.81 kB (67.92 kB gzip), schemas 67.26 kB (18.16 kB gzip), CSS 53.93 kB (10.61 kB gzip). No source maps emitted. Local production build and Docker smoke passed; production performance remains unverified because Railway access is unavailable.
