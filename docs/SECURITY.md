# Security and Privacy Checklist

## Before merge/release

- [ ] No credentials, API keys, tokens, cookies, or private endpoints are committed.
- [ ] Only lawful public-source data is used.
- [ ] Source anonymization is preserved.
- [ ] No deanonymization or identity inference is introduced by transformations.
- [ ] Release/status artifacts contain no secrets.
- [ ] External publishing destinations are authenticated only through GitHub/Kaggle/Hugging Face secret stores.
- [ ] Workflow permissions are the minimum required.
- [ ] Third-party Actions are pinned to immutable revisions where practical.

## Automated control

SEC-01 is enforced by `.github/workflows/security-scan.yml` on pushes and pull requests to `main`. `scripts/security_scan.py` scans tracked text files for high-confidence credential patterns, checks the repository privacy markers, and verifies every committed training manifest declares `public_open_data_only` with `deanonymization: false`. The generated evidence contains findings and metadata only, never matched secret values.

A green SEC-01 result is a required security/privacy control for production readiness. The scanner is deliberately conservative: ordinary hashes, public URLs, documented placeholders, and environment-variable references are not treated as committed credentials.

## Incident response

If a secret is suspected to have been committed: stop publication, revoke/rotate the credential at its provider, remove the secret from the current tree, inspect workflow logs/artifacts, and document the incident. Git history cleanup is secondary to credential revocation.
