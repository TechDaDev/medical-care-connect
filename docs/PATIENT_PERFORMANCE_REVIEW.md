# Patient Performance Review

Measured backend query ceilings:

| Operation | Ceiling |
|---|---:|
| Patient dashboard | 9 exact |
| Doctor list | 5 |
| Doctor detail | 3 |
| Consultation creation | 14 |
| Consultation list | 8 |
| Consultation detail | 8 |
| Patient record list | 7 |
| Patient record detail/profile | 5 |
| Message thread overview | 7 |
| Notification list | 7 |
| Notification mark-all | 5 |
| Export/deletion lookup | 4 |

Tests populate repeated relations to detect N+1 growth. Querysets use
`select_related`, `prefetch_related`, annotations, bounded pagination, and
database filtering. Cancellation locks only consultation row and keeps
side-effects inside transaction.

Frontend uses route-level lazy loading and React Query cache keys scoped by
patient filters/resource identifiers. Mutations invalidate related dashboard,
detail, list, unread, and privacy keys. Production build output is reviewed for
chunk warnings.

These are regression ceilings, not latency SLOs. No production load test or
medical workload benchmark is claimed.
