# Observability

The platform status is represented by machine-readable artifacts under `artifacts/status/` and can be rendered by the Pages dashboard.

## Canonical status index

`artifacts/status/status-index.json` is the canonical repository-level control-plane snapshot. It carries the release identity and the operational signal set in one safe JSON document. The release manifest remains the source of file-level integrity evidence.

The status index must reference the exact `git_commit` recorded by `artifacts/status/release-manifest.json`. A mismatch is a release-contract failure, not a cosmetic dashboard problem.

## Producer signals

Producer workflows publish one JSON signal per operational subsystem as a workflow artifact named `status-signal-<signal>`. The signal schema is intentionally small: schema version, signal name, state, bounded human-readable detail, source commit, timestamp, workflow identity, and optional artifact reference.

A producer signal is accepted into the canonical index only when its `source_commit` matches the release manifest commit. Signals from another release are downgraded to `unknown` rather than silently carried forward. This prevents a successful graph or training result from being displayed as current after the repository has moved on.

The standard writer is `scripts/write_status_signal.py`; producers should call it after their validation/publication gate, including with `if: always()` when a red failure signal is useful. Secrets, credentials, private URLs, and sensitive personal data must never be placed in the signal payload.

## Workflow-run control plane

`.github/workflows/release-control-plane.yml` reacts to completed producer and security workflows, checks out the triggering run's exact `head_sha`, downloads its status-signal artifact, regenerates the release manifest, and produces a canonical status snapshot. This avoids committing transient health signals back into the repository, which would otherwise change the commit being described and create a self-referential identity problem.

The aggregation implementation is `scripts/aggregate_status_signals.py`. It accepts only schema-valid signals whose source commit matches the release manifest. Missing producer or control-plane signals remain `unknown`; malformed signals become `red`; stale signals become `unknown`.

SEC-01 publishes a `status-signal-security` artifact from the Security scan workflow. The control plane consumes that result instead of assuming security is green. Security signals use the same source-commit and freshness checks as operational signals, with a 48-hour freshness window.

## Signals

| Signal | Meaning | Healthy condition |
|---|---|---|
| `ci` | repository validation | latest validation succeeded |
| `ingestion` | source freshness | latest successful ingestion is within its expected cadence |
| `quality` | data contract | all release gates pass |
| `graph` | entity graph | latest build completed successfully |
| `training` | model training | latest expected run has a recorded result |
| `publication` | HF publication | artifact revision is recorded |
| `security` | repository safety | latest SEC-01 scan is green and fresh |

Signals without a trustworthy status artifact are explicitly `unknown`; they must not be represented as healthy merely because the repository CI passed.

## Failure semantics

- **green**: healthy and current
- **yellow**: stale, degraded, or warning condition
- **red**: failed quality/release gate or unrecoverable workflow failure
- **unknown**: no trustworthy producer signal has been recorded yet

## Operational principle

Prefer explicit machine-readable state over parsing human log text. Dashboards consume status artifacts; workflows produce them; source and release manifests explain why a state exists.
