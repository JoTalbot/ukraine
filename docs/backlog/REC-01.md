# REC-01 — Stage-level recovery and replay checkpoints

## Problem

Workflow-level completion checkpoints prove that a producer run finished, but they do not identify the last completed stage when a long-running ingestion, graph, or training run fails. Recovery must be able to resume from a specific completed stage without manually editing generated state.

## Contract

- Recovery Checkpoints must derive stage checkpoints from the completed producer workflow run's actual job steps.
- Each stage checkpoint must carry the exact producer workflow name, source commit, producer run identity, stage identity, state, and a stable idempotency key.
- Stage checkpoints use the existing checkpoint writer and schema; stage identity is part of the idempotency key so stages cannot overwrite one another.
- Only successful stages are trusted for resume. Failed, paused, cancelled, skipped, and in-progress stages remain non-trusted evidence.
- Stage ordering must be deterministic and independent of wall-clock timing.
- The replay manifest must expose the ordered stage chain, trusted successful stages, referenced artifacts when available, and a deterministic next action.
- Recovery metadata must remain bounded and must not contain secrets or sensitive personal data.
- Publication remains behind existing validation and quality gates; a replay plan is not publication authorization.

## Acceptance criteria

- The recovery workflow converts producer job-step outcomes into stage-level checkpoints for ingestion, graph, and training producers.
- Stage checkpoint IDs are stable for the same workflow/source/run/stage identity and distinct across stages.
- The replay manifest orders stages deterministically and identifies the last trusted successful stage.
- Tests cover deterministic stage extraction, failed-stage trust boundaries, and replay next-action selection.
- Existing workflow-level recovery and REC-02 deterministic replay remain backward compatible.
- A real GitHub Actions recovery run validates the new stage-level checkpoint and replay artifacts successfully.
