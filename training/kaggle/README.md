# Kaggle GPU training

This directory contains the reproducible handoff for GPU training from GitHub Actions to Kaggle.

## Pipeline

1. GitHub Actions builds the public-data training manifest.
2. Kaggle consumes the prepared dataset/corpus.
3. GPU training produces checkpoints and evaluation metrics.
4. The resulting model can be published to Hugging Face Model Hub.

## Scope

Training is restricted to lawfully available public/open datasets already admitted by the project's data catalog. Source provenance must be retained. Source-provided anonymization is not reversed.

## Required secrets

- `KAGGLE_API`: stored only as a GitHub Actions repository secret.
- `HF_TOKEN`: stored only as a GitHub Actions repository secret when publishing models.

Secrets must never be committed to this repository or printed in CI logs.

## GPU execution

The GitHub workflow validates authentication and prepares the handoff. Actual GPU compute is performed by a configured Kaggle Notebook/Job, because GitHub-hosted runners do not provide the required GPU runtime.
