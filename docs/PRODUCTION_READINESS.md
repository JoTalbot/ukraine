# Production readiness contract

The final hardening track is implemented as deterministic, machine-readable contracts.

- **DRIFT-01:** `scripts/production_hardening.py drift` compares versioned schema, row count, field distributions, and source availability. Default row-count tolerance is 20%; schema/distribution changes fail closed.
- **QUAR-01:** `quarantine` copies a failed artifact into an immutable digest-qualified quarantine location and writes recovery metadata. Publication must consume only non-quarantined artifacts.
- **REG-01:** `registry` records immutable model IDs, artifact checksums, dataset revision, schema hash, evaluation evidence, and publication state. Reusing a model ID with changed metadata fails.
- **COMPAT-01:** `compat` requires exact dataset revision and schema-hash equality between model and dataset metadata.
- **PROM-01:** `promote` enforces `dev -> validated -> candidate -> production` and requires compatibility, evaluation, and finally readiness gates.
- **ROLL-01:** `rollback` selects the most recent other production model as the last-known-good target and emits an idempotent rollback plan. It fails closed when no target exists.
- **READY-01:** `scripts/check_production_readiness.py` aggregates documentation, control-plane, recovery, dependency, SBOM, provenance, and hardening-contract gates into one deterministic JSON decision. A red gate exits non-zero.

## Operating policy

1. Never publish a quarantined artifact.
2. Never overwrite an existing model registry identity with different lineage or bytes.
3. Never promote across states while a required gate is red.
4. Rollback targets are selected by recorded production state, not by mutable filenames.
5. Generated readiness evidence is an output, never an input to its own decision.
6. Baselines for drift are versioned inputs. A new dataset establishes a baseline only through an explicit review/change, not by silently replacing the previous baseline.
