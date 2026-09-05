# SEC-02 — Security signal control-plane binding

## Goal

Bind the SEC-01 security/privacy scan result to the canonical release control-plane status instead of treating security as an unconditional green signal.

## Acceptance criteria

- The Security scan workflow emits the standard `security` status signal with source commit and workflow/run identity.
- The Release Control Plane listens for completed Security scan runs and consumes the `status-signal-security` artifact.
- Missing, malformed, stale, future-dated, or wrong-commit security signals fail closed according to the canonical status policy.
- The canonical status index no longer hard-codes `security=green`.
- Deterministic tests cover security signal validation and control-plane aggregation.
- Documentation and roadmap status are updated before implementation is considered complete.

## Scope

Only control-plane observability is changed. SEC-01 scan semantics remain unchanged.

## Operating rule

Do not weaken the privacy/security scan to make aggregation pass. The control plane must reflect the actual SEC-01 result.

## Status

**Implemented and runtime-verified.** Security scan #26 emitted the standard `security` signal, and Release Control Plane #250 consumed the producer artifact successfully. Unit coverage verifies preserved state, missing-signal `unknown`, wrong-commit rejection, stale-signal rejection, and invalid-schema `red` behavior.
