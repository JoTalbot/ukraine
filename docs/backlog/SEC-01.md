# SEC-01 — Automated security/privacy boundary scan

## Goal

Turn the repository security/privacy checklist into a deterministic CI control instead of a manual checklist.

## Contract

Every security scan must:

1. inspect tracked repository text files for high-confidence credential/token patterns;
2. reject private endpoint configuration and obvious secret-bearing environment assignments;
3. verify the repository's explicit `no_deanonymization` policy markers remain present;
4. verify training manifests declare `public_open_data_only` and `deanonymization: false`;
5. emit machine-readable evidence with source commit, workflow/run identity when supplied, deterministic findings, and a stable policy result;
6. fail closed on findings or broken privacy-policy assertions.

The scanner must avoid treating ordinary documentation words, hashes, public URLs, or example placeholders as secrets. It must never print matched secret values.

## Acceptance criteria

- `scripts/security_scan.py` provides deterministic repository and policy checks.
- Unit tests cover credential detection, false-positive exclusions, privacy markers, and manifest policy.
- CI runs the scan on every push and pull request to `main`.
- Security evidence is uploaded as a workflow artifact without secret material.
- `docs/SECURITY.md` records the automated control and its incident-response boundary.

## Status

Implemented and runtime-verified.
