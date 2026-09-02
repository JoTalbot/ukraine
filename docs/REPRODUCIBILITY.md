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

## Evaluation

Model releases must retain evaluation configuration, dataset identity, metric values, and training configuration. Metrics are evidence, not decoration. A missing metric is a failed gate, not a reason to publish a pretty README.

## Recovery

Jobs must be idempotent. Generated state is disposable; source manifests and release manifests are authoritative. Failed jobs should be rerunnable without manually editing generated files.
