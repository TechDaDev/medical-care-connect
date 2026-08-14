# ADR 0005: Doctor-safe AI intake projection

Status: Accepted — 2026-08-14

Decision: expose one assigned-doctor endpoint with explicit safe projection and same-session evidence IDs. Keep medical-record authorship separate. Reject generic session serialization because it risks hidden/provider/internal data leakage and weakens authorization locality.
