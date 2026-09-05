# Release Candidate Record

This file is a release-process marker only. The authoritative release identity is the Git tag and commit selected after all automated gates pass.

## Required evidence

- Ukraine data CI: success
- Security scan: success
- Release Control Plane: success
- READY-01: green
- Release/status validation: success
- Runtime hardening evidence: success
- Release manifest: generated and validated
- SBOM: generated
- Canonical control-plane snapshot: uploaded

Do not edit generated evidence manually. The release candidate is valid only when all evidence belongs to the same source commit.
