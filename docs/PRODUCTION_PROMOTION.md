# Production Promotion Authorization

Production promotion is intentionally a separate approval step. The Release Control Plane must fail closed when authoritative authorization is absent.

## Flow

1. Identify the exact release commit SHA.
2. Confirm the upstream data and security gates for that SHA are successful.
3. Start `Production Promotion Authorization` manually with the exact model ID, artifact SHA-256, evaluation-evidence SHA-256, approval identity, and positive release sequence.
4. The `production` GitHub Environment is the approval boundary. Its required reviewers must approve before the authorization job can execute.
5. The workflow verifies the exact source commit and upstream gates, then emits `production-promotion-authorization.json` as an immutable workflow artifact.
6. Release Control Plane consumes that artifact for the same source SHA and verifies its contents before cryptographic-chain and READY-01 evaluation.

The authorization artifact is deliberately not committed to `main`. Committing it would change the source commit it authorizes and create a self-invalidating release identity.

## Fail-closed rules

- No authorization artifact means no production promotion.
- Authorization for a different source commit is rejected.
- Invalid SHA-256 values, missing approval identity, non-production target, or non-positive release sequence are rejected.
- The workflow must never manufacture approval identity or bypass the GitHub Environment approval boundary.

## Current state

The repository previously had verification for authoritative authorization but no producer for it. The new workflow closes that architectural gap. Production remains red until a real production Environment approval is granted for a valid release candidate.
