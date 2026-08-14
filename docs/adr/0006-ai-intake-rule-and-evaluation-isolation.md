# ADR 0006: Emergency-rule and evaluation isolation

Status: Accepted — 2026-08-14

Decision: isolate deterministic language rules from model prompts and isolate evaluation from runtime patient workflows. Evaluation is mock-first, synthetic-only, and live-gated. Backend emergency/completeness state always overrides model suggestions.
