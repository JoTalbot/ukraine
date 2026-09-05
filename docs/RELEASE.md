# Release Protocol

## Production release gate

A production release is created only after the current `main` commit has passed the repository control plane and the release evidence is traceable to that exact commit.

Required evidence:

1. `Ukraine data CI` is successful.
2. `Security scan` is successful and publishes `status-signal-security`.
3. `Release Control Plane` consumes the producer security signal and evaluates `READY-01` successfully.
4. Release and status contract validation is successful.
5. Runtime hardening evidence self-test is successful.
6. The release manifest and SBOM are generated successfully.
7. The canonical status snapshot is uploaded as a workflow artifact.
8. No required signal is missing, stale, malformed, or bound to another commit.

## Reproducibility

The release manifest is the authoritative file-level provenance record. Reproducibility comparison is performed on reproducibility-bearing fields, while workflow execution IDs and timestamps may differ between runs.

## Security

SEC-01 is a fail-closed production control. A missing security signal is not treated as green. The control plane must consume the standard `status-signal-security` artifact emitted by the Security scan workflow.

## Recovery

Generated artifacts are disposable. Source manifests, release manifests, and committed code are authoritative. Failed workflows must be rerunnable without manual editing of generated state.

## Release checklist

- [ ] Current `main` SHA recorded.
- [ ] CI green.
- [ ] Security green with matching source commit.
- [ ] Control plane green and READY-01 green.
- [ ] Release manifest validated.
- [ ] SBOM generated.
- [ ] Hardening evidence validated.
- [ ] Canonical control-plane snapshot uploaded.
- [ ] Release tag points to the verified commit.
- [ ] GitHub Release notes reference the exact tag/commit and evidence artifacts.
