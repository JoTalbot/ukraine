# Production readiness contract

The final hardening track is implemented as deterministic, machine-readable contracts.

- **DRIFT-01:** `scripts/production_hardening.py drift` compares versioned schema, row count, field distributions, and source availability. Default row-count tolerance is 20%; schema/distribution changes fail closed.
- **QUAR-01:** `quarantine` uses the full SHA-256 in the content-addressed target name, verifies an existing target before reuse, and verifies the copied bytes after creation. A digest mismatch fails closed.
- **REG-01:** `registry` records immutable model IDs, artifact checksums, dataset revision, schema hash, evaluation evidence, and publication state. Reusing a model ID with changed metadata or bytes fails.
- **COMPAT-01:** `compat` requires exact dataset revision and schema-hash equality between model and dataset metadata.
- **PROM-01:** `promote` enforces `dev -> validated -> candidate -> production`. Production promotion additionally requires model ID, artifact SHA-256, evaluation-evidence SHA-256, approval identity, positive immutable release sequence, and promotion timestamp, and emits a machine-readable promotion event.
- **ROLL-01:** `rollback` refuses candidates without immutable `release_sequence` and `promoted_at`, then selects the highest recorded release sequence and emits an atomic-switch plan. It fails closed when no last-known-good target exists.
- **CHAIN-01:** `scripts/verify_artifact_chain.py` verifies the release manifest's own file checksums and binds the release manifest, SBOM, status index, and runtime hardening evidence by SHA-256 without introducing a circular hash dependency.
- **READY-01:** `scripts/check_production_readiness.py` aggregates documentation, control-plane, recovery, dependency, SBOM, provenance, hardening, artifact-chain, and authoritative-promotion gates into one deterministic JSON decision. A red gate exits non-zero.

## Operating policy

1. Never publish a quarantined artifact.
2. Never overwrite an existing model registry identity with different lineage or bytes.
3. Never promote across states while a required gate is red.
4. Production promotion must carry a machine-readable artifact/evaluation binding, approval identity, release sequence, and UTC timestamp.
5. Rollback targets must have immutable promotion metadata; the deployment layer must perform the emitted atomic switch and record the event.
6. Generated readiness evidence is an output, never an input to its own decision.
7. Baselines for drift are versioned inputs. A new dataset establishes a baseline only through an explicit review/change, not by silently replacing the previous baseline.
8. `bootstrap_complete=true` is valid only when every catalog batch is present in `successful_batches` and `failed_batches` is empty.
