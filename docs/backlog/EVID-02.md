# EVID-02 — Readiness evidence parity across CI workflows

## Problem

READY-01 now requires runtime hardening evidence. Any workflow that invokes the readiness gate must therefore generate the same evidence first; otherwise a valid CI run can fail solely because its evidence-producing step is absent.

## Contract

- Every workflow that invokes `scripts/check_production_readiness.py` must first execute `scripts/production_hardening.py evidence`.
- Evidence must use the exact workflow source SHA and GitHub workflow/run identity.
- Readiness remains fail-closed when evidence is missing, malformed, stale, or incomplete.
- The generated evidence remains ephemeral CI output and is never used as source input to its own decision.
- The Release Control Plane is itself a READY-01 caller and must generate evidence immediately before evaluating readiness, including on `workflow_run` executions where the checked-out source SHA is the producer run's `head_sha`.

## Acceptance criteria

- Ukraine data CI generates hardening evidence before READY-01.
- Release observability continues to generate evidence before READY-01.
- Release Control Plane generates hardening evidence immediately before READY-01 with the exact checkout/source SHA and control-plane workflow/run identity.
- CI tests prove both the positive and missing-evidence paths.
- A repository-level contract test prevents a future READY-01 workflow caller from omitting the evidence step.
