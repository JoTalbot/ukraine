# Ukraine Platform Roadmap

## Definition of done

The repository is considered production-ready when every automated data/model release is traceable, validated, reproducible, observable, privacy-safe, and recoverable without manual editing of generated state.

## Completed foundations

- Official-source ingestion and discovery.
- SHA-256 integrity checks and Parquet normalization.
- EDRSR synchronization and Hugging Face publication.
- Entity-link graph construction.
- CPU/GPU model-training paths.
- GitHub Actions orchestration, failure alerts, Pages dashboard, and race-safe persistence.
- Repository-level release manifests with commit identity, runtime metadata, and file checksums, published as CI artifacts.
- Release-manifest schema validation covering identity, UTC timestamp, file uniqueness, SHA-256 format, excluded paths, and byte-size integrity.
- Pages dashboard release identity: generated manifest commit, branch, UTC timestamp, and file count are surfaced alongside operational model/data status.
- Canonical machine-readable platform status index linking operational signals to the exact release manifest identity.
- Standard producer-signal schema and writer for ingestion, quality, graph, training, and publication workflows.
- Workflow-run control-plane aggregation foundation with external signal artifacts, exact source-commit matching, stale-signal rejection, and canonical snapshot publication.
- Entity Graph producer integrated with the standard `graph` signal artifact contract.

## Final hardening track

1. **Data contracts** — validate source manifests, schemas, required metadata, checksums, and non-empty outputs before publication.
2. **Quality gates** — detect malformed records, duplicate IDs, suspicious row-count changes, missing provenance, and schema drift.
3. **Lineage/provenance** — record source URL, retrieval time, source version/ETag, checksum, transformation version, and artifact revision.
4. **Reproducibility** — pin CI actions, Python dependencies, deterministic build metadata, and release manifests.
5. **Model evaluation** — keep immutable evaluation metadata and reject publication when required metrics are missing or regress beyond configured thresholds.
6. **Release management** — generate machine-readable release manifests and human-readable release notes for data, graph, and model artifacts.
7. **Security/privacy** — continuously scan repository configuration and enforce the existing no-deanonymization boundary.
8. **Observability** — expose health, freshness, quality, training, publication, and failure signals in one status artifact; wire every producer workflow to the standard signal contract.
9. **Recovery** — make failed runs resumable/idempotent and preserve enough state to diagnose and replay them.
10. **Documentation** — keep architecture, operational procedures, data contracts, and release criteria in-repository.

## Newly identified hardening items

- **OBS-01 — Producer signal aggregation:** collect workflow artifacts from completed producer runs and reconcile them into the canonical status index without copying stale signals forward. **Foundation implemented; remaining work is to wire all producer workflows.**
- **OBS-02 — Action pinning audit:** replace mutable GitHub Action tags with immutable commit SHAs where practical, matching the reproducibility policy. **Implemented and verified by CI.**
- **OBS-03 — Release validation consolidation:** remove duplicated inline manifest/status validation from CI and use the tested `validate_release.py` contract as the single validator. **Implemented in Ukraine data CI and Release observability.**
- **REC-01 — Recovery/replay contract:** define durable checkpoints, idempotency keys, replay manifests, and last-successful state for long-running ingestion, graph, and training workflows. **Workflow-level durable completion checkpoints integrated for core producer workflows; stage-level replay remains future hardening.**
- **CTRL-01 — Unified control-plane policy:** define freshness windows, producer priority, and status precedence so the dashboard can distinguish missing, stale, degraded, and current signals across independent schedules. **Policy foundation implemented.**

## Production readiness backlog

- **DEP-01 — Deterministic dependency lock:** pin CI/runtime Python dependencies and verify the lock is consumed by every relevant workflow. **Baseline lock implemented; dedicated Hugging Face publisher partition added and adopted by EDRSR publisher.**
- **SUP-01 — SBOM and supply-chain evidence:** publish a machine-readable SBOM plus dependency provenance with every release-control snapshot. **Implemented and bound to the canonical status index.**
- **PROV-01 — Artifact provenance:** bind generated artifacts to source commit, workflow run, inputs, toolchain, and checksums. **Implemented through release-manifest execution evidence and checksum validation.**
- **REPRO-01 — Reproducibility verification:** provide a deterministic verification path that compares repeated generated outputs/manifests and rejects unexplained drift. **Implemented with repeated-manifest comparison in Release observability.**
- **DRIFT-01 — Data drift detection:** monitor schema, row-count, field-distribution, and source-availability drift against versioned baselines. **Contract implemented in `scripts/production_hardening.py`; fails closed on schema/distribution/source drift and configurable row-count thresholds.**
- **QUAR-01 — Automatic quarantine:** isolate failed or suspicious datasets/artifacts from publication while retaining diagnostics and recovery metadata. **Contract implemented with digest-qualified quarantine copies and provenance marker.**
- **REG-01 — Model registry:** maintain immutable model versions with evaluation, dataset lineage, and publication state. **Contract implemented with immutable model IDs and artifact checksums.**
- **COMPAT-01 — Dataset/model compatibility:** enforce compatibility between model artifacts and the exact dataset/schema lineage used for training. **Contract implemented with exact dataset revision and schema-hash matching.**
- **PROM-01 — Release promotion:** formalize dev → validated → candidate → production promotion states with explicit gates. **Contract implemented with fail-closed state transitions and readiness/evaluation/compatibility gates.**
- **ROLL-01 — Automatic rollback:** retain the last known-good release and provide a safe, idempotent rollback path. **Contract implemented with recorded production targets and an atomic rollback plan; fails closed when no target exists.**
- **READY-01 — Production readiness gate:** aggregate all hardening checks into one deterministic machine-readable readiness decision. **Implemented in `check_production_readiness.py`, exercised by CI, and published with release/control-plane snapshots.**

## Implementation improvements discovered during hardening

- **DEP-02 — Lock completeness contract:** the lock must include direct CI requirements plus all transitive packages required by those requirements, so `pip install -r requirements.lock` is self-contained and reproducible. **Implemented.**
- **PROV-02 — Release execution identity:** release evidence should include workflow name/run ID and explicit input/toolchain metadata rather than relying on commit identity alone. **Implemented.**
- **REPRO-02 — Generated-state exclusion:** reproducibility manifests must exclude their own mutable output and transient interpreter/build caches to avoid self-referential hashes. **Implemented.**
- **REG-02 — Unified model publication quality gate:** every automated model publisher must compare the candidate evaluation metric with the currently published model and block publication on unexplained regression; a missing baseline is allowed only for an initial publication. **Existing model publication gate retained; registry now records the immutable evaluation evidence.**
- **REC-02 — Deterministic replay manifest:** recovery must preserve a bounded, machine-readable replay plan containing source commit, workflow/run identity, completed checkpoints, artifact references, and explicit next action, so replay does not depend on interpreting logs or manually editing generated state. **Existing recovery checkpoint contract retained and exposed to readiness.**
- **PROV-03 — Release manifest execution evidence:** generated release manifests should carry workflow/run identity, trigger type, source SHA, and runtime/toolchain metadata so evidence remains attributable to the exact execution context. **Implemented.**
- **SUP-02 — SBOM control-plane binding:** the canonical status index should reference the exact generated SBOM and its checksum, making supply-chain evidence discoverable and cryptographically bound to the release snapshot. **Implemented.**
- **DEP-03 — Workflow lock partitioning:** workflows with materially different dependency indexes, such as Hugging Face publishers or GPU training, must use dedicated deterministic lock files rather than silently installing mutable latest packages. **Hugging Face publisher partition implemented; GPU/Kaggle remains intentionally isolated because its CUDA/package-index contract is hardware-specific and is not safely interchangeable with CPU CI.**
- **EVID-01 — Runtime hardening evidence:** READY-01 must validate execution evidence for DRIFT, QUAR, REG, COMPAT, PROM, and ROLL, not merely the presence of their contract code. Evidence must be generated from deterministic self-tests in CI, include the exact source commit and workflow identity, and be treated as generated output rather than readiness input. **Implemented and tested.**
- **EVID-02 — Readiness evidence parity across CI workflows:** every workflow invoking READY-01 must generate deterministic hardening evidence immediately before the readiness gate, using the exact checkout SHA and workflow/run identity. **Implemented and enforced in Ukraine data CI, Release observability, and Release Control Plane; repository-level caller coverage test added.**

## Operating rule

When a useful improvement is discovered during implementation, add it to this roadmap or an explicit backlog entry before applying it. Do not silently drop product or architecture changes.
