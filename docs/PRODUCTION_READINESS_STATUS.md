# Production Readiness Status

## 2026-09-15

### Current release

- Main revision: `7c274020a2cfed1d65a73acfb150d893e6977751`
- Previous release-control-plane dispatcher fix: `e48576ee370b19c0d9a310cd2e0b9159d6eac944`

### Verified

- `Ukraine data CI` for `e48576ee370b19c0d9a310cd2e0b9159d6eac944` completed successfully.
- CI completed lint, compilation, unit tests, release manifest, SBOM, status index, release validation, hardening evidence, and quality signal publication.
- `Recovery Checkpoints` completed successfully, including checkpoint validation and deterministic replay manifest validation.
- Failure alert processing completed successfully.

### Orchestration hardening

The release dispatcher previously preferred the API's ordering of successful quality runs. This could select an older successful release and postpone the current `main` revision. It was first corrected to prioritize `GITHUB_SHA`.

A second hardening pass now prevents `push` and manual dispatch executions from falling back to an older release at all. They operate only on the current revision. Scheduled recovery retains the ability to process older successful candidates. This separates normal release progression from recovery and prevents stale releases from starving the current one.

### Production gate

Production readiness remains **NOT GREEN** until the complete same-SHA chain is verified:

`Ukraine data CI → ingestion → graph → training → publication → security → Release Control Plane → Production Release Gate`

Individual successful workflows do not constitute production readiness. Historical runs are not accepted as evidence for a new release.

### Next verification

Verify that the new dispatcher revision `7c274020a2cfed1d65a73acfb150d893e6977751` launches cleanly and that producer workflows are attached to the intended immutable release candidate. If a producer fails, repair the workflow and rerun the affected stage without weakening same-SHA guarantees.
