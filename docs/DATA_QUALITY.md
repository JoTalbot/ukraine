# Data Quality and Release Contract

Every published dataset, graph, or model must have enough metadata to answer: where did it come from, what changed it, when was it produced, and what validation passed?

## Minimum provenance

- source identifier and canonical URL
- retrieval timestamp in UTC
- source version, ETag, Last-Modified, or equivalent when available
- SHA-256 of the retrieved input
- transformation/build revision
- output artifact identifier and checksum when available
- license/attribution information

## Quality gates

A publication job must fail closed when:

- required manifest fields are absent;
- an expected schema is missing or invalid;
- an output is unexpectedly empty;
- a stable primary key contains duplicates;
- a checksum is malformed;
- provenance is absent;
- model evaluation metadata is incomplete when the release is a model release.

Large row-count changes are a warning rather than an automatic failure unless a dataset-specific contract explicitly defines bounds. Public sources can legitimately change dramatically, and pretending otherwise is how dashboards become fiction.

## Privacy boundary

Only lawfully published open data may enter the pipeline. Do not reverse anonymization, infer protected identifiers, ingest credentials/secrets, or add private-source data. Transformations must preserve source-imposed anonymization.

## Release rule

Validation happens before publication. The generated status/release manifest is an auditable record and must not contain secrets or personal authentication material.
