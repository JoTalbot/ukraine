# Ukraine Data Platform

## Production release

This release establishes the production control-plane baseline for auditable Ukraine public-data, graph, and model artifacts.

### Included

- Traceable release manifests with commit identity and file checksums.
- Deterministic dependency installation and SBOM generation.
- Canonical release status aggregation across data, graph, training, publication, and security controls.
- Fail-closed security/privacy validation through SEC-01 and SEC-02.
- Runtime hardening evidence and READY-01 production-readiness gating.
- Stage-level recovery checkpoints and replay manifests.
- Release observability and reproducibility contracts.

### Security

The security status is a real producer signal. The Security scan workflow publishes `status-signal-security`, and the Release Control Plane consumes that artifact for the exact release commit. Missing or invalid evidence cannot silently become green.

### Verification

The release tag must be created only from the commit whose CI, security scan, control-plane aggregation, hardening evidence, and production-readiness checks are all successful.
