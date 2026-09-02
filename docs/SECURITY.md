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

## Incident response

If a secret is suspected to have been committed: stop publication, revoke/rotate the credential at its provider, remove the secret from the current tree, inspect workflow logs/artifacts, and document the incident. Git history cleanup is secondary to credential revocation.
