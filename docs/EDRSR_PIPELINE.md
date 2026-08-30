# ЄДРСР data pipeline

## Objective

Build a reproducible pipeline from official ЄДРСР open-data publications to a machine-readable Hugging Face Dataset, without committing the large source archives to Git.

## Stages

1. **Discover** — resolve the current official open-data publication and its metadata.
2. **Acquire** — download the selected annual archive to ephemeral CI storage.
3. **Verify** — calculate SHA-256 and record source metadata before processing.
4. **Extract** — unpack the archive without following unsafe paths.
5. **Normalize** — map source fields to `schemas/edrsr-record.schema.json`; preserve unknown fields for provenance where practical.
6. **Convert** — write partitioned Parquet with stable UTF-8 text and explicit schema.
7. **Quality checks** — validate required fields, duplicate identifiers, parseable dates, non-empty text, row counts, and deterministic manifests.
8. **Publish** — upload only generated dataset artifacts to the configured Hugging Face Dataset repository.
9. **Index** — build full-text and vector indexes downstream; indexes are derived artifacts and must be reproducible from the dataset.
10. **Operate** — run incrementally/daily, retaining manifests so failed or repeated runs are detectable.

## Data governance

Do not put personal data, source archives, tokens, or generated indexes into the Git repository. Respect the official publication terms and any applicable Ukrainian law. Keep provenance and source attribution with every published dataset revision.

## Initial publication target

`JoTalbot/ua-edrsr` on Hugging Face, subject to creation/permission of that Dataset repository.
