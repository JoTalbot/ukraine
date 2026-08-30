# Architecture

## Data flow

```text
Official ЄДРСР open data
        ↓
   ingestion/sync
        ↓
 checksum + provenance manifest
        ↓
       raw archive
        ↓
 parsing / normalization
        ↓
      Parquet Dataset
        ↓
 Hugging Face Dataset
        ↓
 embeddings + lexical index
        ↓
     API / RAG / search
```

## Design rules

1. Official-source provenance is preserved for every import.
2. Raw archives are not treated as the query database.
3. Parquet is the canonical AI-ready interchange format.
4. Search indexes are reproducible from the normalized dataset.
5. Incremental updates must be idempotent.
6. Secrets and access tokens live only in GitHub/Hugging Face secret stores, never in Git history.

## Initial scope

Start with yearly official archives, then add incremental daily refreshes when the source format and availability are verified.
