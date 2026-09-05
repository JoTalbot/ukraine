# Production Release Protocol

A production release is created only from a `main` commit whose automated release evidence is traceable to that exact commit.

Required gates:

1. Ukraine data CI succeeds.
2. Security scan succeeds and publishes `status-signal-security`.
3. Release Control Plane consumes that security artifact for the same source commit.
4. Release/status validation succeeds.
5. Runtime hardening evidence succeeds.
6. READY-01 production readiness is green.
7. Release manifest and SBOM are generated and uploaded.
8. The release tag points to the verified commit.

Security is fail-closed: missing, malformed, stale, or wrong-commit signals cannot become green. Generated state is disposable; manifests and source revisions are authoritative.
