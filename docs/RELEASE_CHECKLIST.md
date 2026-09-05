# Production Release Checklist

Use the latest `main` commit only. A release is valid when all automated evidence belongs to the same commit.

- Ukraine data CI: success
- Security scan: success
- `status-signal-security`: published
- Release Control Plane: success
- READY-01: green
- Release/status validation: success
- Runtime hardening evidence: success
- Release manifest: validated
- SBOM: generated
- Canonical control-plane snapshot: uploaded
- Release tag: points to the verified commit
