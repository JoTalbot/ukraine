# Data layout

Large ЄДРСР datasets are not committed to Git. Git stores schemas, manifests, ingestion code, and reproducibility metadata; Hugging Face stores the generated datasets.

Planned layers:

- `raw/` — local/CI staging only, never committed
- `normalized/` — Parquet staging only
- `manifests/` — checksums, source dates, row counts and provenance
- Hugging Face Dataset — canonical large-data distribution

Source: official open-data publications of the State Judicial Administration of Ukraine / ЄДРСР. Verify the current source URL and licence before every ingestion run.
