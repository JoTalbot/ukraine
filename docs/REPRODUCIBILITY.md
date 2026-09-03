# Reproducibility and Release Protocol

## Build identity

Every release should identify:

- Git commit SHA
- UTC build timestamp
- Python/runtime version
- relevant dependency lock or pinned CI action revisions
- source manifest revision
- transformation code revision
- model configuration and training-data identity for model releases

## Release classes

- `data` — normalized public datasets
- `graph` — entity-link graph artifacts
- `model` — trained model/tokenizer/evaluation artifacts

Each release class uses the same provenance contract and can be replayed from the recorded source and code revisions, subject to source availability.

## Deterministic verification

A release manifest contains the reproducibility-bearing snapshot: schema version, release class, Git commit, branch, Python runtime, and every tracked file checksum/size. Execution identity and wall-clock generation time are deliberately excluded from reproducibility equality because repeated runs legitimately have different workflow IDs and timestamps.

Two manifests for the same source revision can therefore be compared with `compare_release_manifests()` from `scripts/validate_release.py`. The comparison rejects any drift in reproducibility-bearing fields while allowing a distinct generation timestamp and execution identity. A reproducibility check must be performed only after each manifest has independently passed the release-contract validator.

The manifest generator excludes its own mutable output and transient Python cache files, preventing self-referential hashes and interpreter cache noise from producing false drift.

## Evaluation

Model releases must retain evaluation configuration, dataset identity, metric values, and training configuration. Metrics are evidence, not decoration. A missing metric is a failed gate, not a reason to publish a pretty README.

## Recovery

Jobs must be idempotent. Generated state is disposable; source manifests and release manifests are authoritative. Failed jobs should be rerunnable without manually editing generated files.
