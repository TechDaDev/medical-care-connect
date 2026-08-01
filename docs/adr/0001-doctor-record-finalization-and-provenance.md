# ADR 0001: Doctor record finalization and provenance

- Status: accepted
- Date: 2026-08-01

## Context

Existing record table mixed intake/patient fields, AI-era fields, and doctor notes. Consultation completion required only record existence. Concurrent edits, finalization authority, provenance, patient visibility, and clinical outcomes lacked explicit contracts.

## Decision

Keep existing one-record-per-consultation table for compatibility. Add doctor-authored fields, version, creator/finalizer, provenance, clinical outcome, and action ledger. Use command services with transactions, row locks, optimistic versions, idempotency fingerprints, sanitized audits, and generic notifications. Doctor finalization makes record immutable. Patient projection is finalized-only and allowlisted. Outcomes require finalized record and execute through consultation transition service. Amendments remain unavailable.

## Consequences

Existing record IDs and consultation relationship remain stable. Intake seeding stays distinct from clinical authorship. List queries stay narrative-free. Old doctor-command bypasses are rejected after record is claimed. Phase D must introduce append-only amendment lineage instead of mutating finalized rows.
