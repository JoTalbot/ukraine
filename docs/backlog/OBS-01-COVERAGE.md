# OBS-01-COVERAGE — Producer signal workflow coverage

## Problem

OBS-01 has a standard producer-signal schema and control-plane aggregation, but production observability is only complete when every operational producer workflow emits its own current signal artifact. Missing coverage makes the canonical snapshot depend on stale or absent state.

## Contract

- Every operational producer workflow identified by the roadmap emits exactly one standard signal for its producer role.
- Signals include the exact workflow source commit, workflow name, workflow run ID, terminal job state, and relevant artifact reference when one exists.
- Signal generation runs with `always()` semantics so failed producer runs publish a red signal instead of disappearing from the control plane.
- Signal artifacts use the existing `write_status_signal.py` schema and `status-signal-<producer>` artifact naming convention.
- The control plane remains the only component that reconciles producer signals into the canonical snapshot; producers do not mutate generated control-plane state.
- Non-producer/support workflows are explicitly excluded rather than silently treated as healthy producers.

## Acceptance criteria

- Audit all `.github/workflows/*.yml` files and classify producer versus support/control-plane workflows.
- Every producer workflow has a standard signal writer and uploaded signal artifact, or an explicit documented exclusion.
- Signal coverage is enforced by a repository-level test so a new producer cannot silently ship without observability.
- Existing signal-producing workflows continue to validate under CI.
- Documentation and roadmap status are updated with the final coverage matrix.
