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

- **OBS-01 — Producer signal aggregation:** collect workflow artifacts from completed producer runs and reconcile them into the canonical status index without copying stale signals forward.
- **OBS-02 — Action pinning audit:** replace mutable GitHub Action tags with immutable commit SHAs where practical, matching the reproducibility policy.
- **OBS-03 — Release validation consolidation:** remove duplicated inline manifest/status validation from CI and use the tested `validate_release.py` contract as the single validator.

## Operating rule

When a useful improvement is discovered during implementation, add it to this roadmap or an explicit backlog entry before applying it. Do not silently drop product or architecture changes.
