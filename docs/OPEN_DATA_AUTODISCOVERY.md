# Open Data Auto-Discovery

## Purpose

Keep the Ukraine open-data catalog current without manually adding every new dataset.

## Pipeline

`data.gov.ua CKAN API -> discovery -> deduplication -> freshness/quality checks -> catalog candidate -> ingestion -> Parquet -> manifest/checksum -> Hugging Face`

## Rules

1. Prefer official Ukrainian government sources.
2. Do not publish datasets that are explicitly discontinued or no longer updated unless they are marked historical.
3. Deduplicate by dataset identity, source URL, resource URL and normalized title.
4. Classify candidates as P1/P2/P3 based on legal, economic, infrastructure and graph value.
5. Validate schema, file integrity, row counts and freshness before promotion.
6. Preserve source provenance and SHA-256 checksums.
7. Quarantine schema-breaking or suspicious updates instead of silently publishing them.
8. Never commit large raw datasets to Git.

## Current catalog

The curated catalog is maintained in `config/ukraine_open_data_catalog.json`. Discovery is intentionally separate from publication: discovery may find candidates, but only validated candidates become enabled catalog entries.

## Operational target

Run discovery on a schedule, compare results with the catalog, emit a machine-readable report, and feed validated additions into the existing Hugging Face synchronization workflow.

## Release gate

Any catalog or pipeline change must pass the repository's normal validation, reproducibility, observability and production release gates before being considered production-ready.
