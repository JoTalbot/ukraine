# Model Evaluation Policy

The training pipeline may produce candidate models frequently, but publication is a separate quality decision.

## Required metadata

A model result must identify the model revision, training-data revision, training configuration, evaluation configuration, and metric values. If any required field is unavailable, the result remains a candidate and must not be presented as a fully evaluated release.

## Regression policy

Do not hard-code universal metric thresholds across model families. Store baseline metrics with the evaluation manifest and compare like-for-like runs. A regression is actionable when the same evaluation protocol shows a meaningful decline.

## Reproducibility

Evaluation inputs and code revisions must be immutable or content-addressed. Random seeds should be recorded where the training/evaluation implementation supports them.
