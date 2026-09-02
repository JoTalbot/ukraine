# Observability

The platform status is represented by machine-readable artifacts under `artifacts/status/` and can be rendered by the Pages dashboard.

## Canonical status index

`artifacts/status/status-index.json` is the canonical repository-level control-plane snapshot. It carries the release identity and the operational signal set in one safe JSON document. The release manifest remains the source of file-level integrity evidence.

The status index must reference the exact `git_commit` recorded by `artifacts/status/release-manifest.json`. A mismatch is a release-contract failure, not a cosmetic dashboard problem.

## Signals

| Signal | Meaning | Healthy condition |
|---|---|---|
| `ci` | repository validation | latest validation succeeded |
| `ingestion` | source freshness | latest successful ingestion is within its expected cadence |
| `quality` | data contract | all release gates pass |
| `graph` | entity graph | latest build completed successfully |
| `training` | model training | latest expected run has a recorded result |
| `publication` | HF publication | artifact revision is recorded |
| `security` | repository safety | no committed secret-like material is detected |

Signals without a producer-specific status artifact are explicitly `unknown`; they must not be represented as healthy merely because the repository CI passed.

## Failure semantics

- **green**: healthy and current
- **yellow**: stale, degraded, or warning condition
- **red**: failed quality/release gate or unrecoverable workflow failure
- **unknown**: no trustworthy producer signal has been recorded yet

Observability data must be safe to publish. Never include tokens, credentials, private URLs, raw secrets, or sensitive personal data in status artifacts or logs.

## Operational principle

Prefer explicit machine-readable state over parsing human log text. Dashboards consume status artifacts; workflows produce them; source and release manifests explain why a state exists.
