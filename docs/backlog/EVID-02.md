# EVID-02 — Readiness evidence parity across CI workflows

## Problem

READY-01 now requires runtime hardening evidence. Any workflow that invokes the readiness gate must therefore generate the same evidence first; otherwise a valid CI run can fail solely because its evidence-producing step is absent.

## Contract

- Every workflow that invokes `scripts/check_production_readiness.py` must first execute `scripts/production_hardening.py evidence`.
- Evidence must use the exact workflow source SHA and GitHub workflow/run identity.
- Readiness remains fail-closed when evidence is missing, malformed, stale, or incomplete.
- The generated evidence remains ephemeral CI output and is never used as source input to its own decision.

## Acceptance criteria

- Ukraine data CI generates hardening evidence before READY-01.
- Release observability continues to generate evidence before READY-01.
- CI tests prove both the positive and missing-evidence paths.
