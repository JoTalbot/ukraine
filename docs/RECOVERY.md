# Recovery and Replay

Long-running ingestion, graph, and training workflows must be recoverable without manually editing generated state.

## Checkpoint contract

`artifacts/recovery/checkpoints/<checkpoint_id>.json` is the machine-readable checkpoint format. The writer is `scripts/write_recovery_checkpoint.py`.

Each checkpoint records:

- `workflow` — producer workflow identity.
- `source_commit` — exact repository revision being processed.
- `idempotency_key` — stable key for the logical run/input combination.
- `checkpoint` — completed stage, such as `download`, `normalize`, `build`, or `publish`.
- `state` — `running`, `succeeded`, `failed`, or `paused`.
- `checkpoint_id` — SHA-256 derived from workflow, source commit, and idempotency key.
- bounded detail and UTC update time.

The derived checkpoint ID makes repeated writes for the same logical operation address the same state record. A retry must resume from the last trusted successful checkpoint rather than blindly repeating non-idempotent publication.

## Replay rules

1. Never treat a failed checkpoint as successful merely because an output file exists.
2. Reuse only artifacts whose source commit and input identity match the replay request.
3. Publication must remain behind the existing validation gates.
4. Retries must be safe to repeat. External uploads should use stable artifact paths or explicit revision metadata.
5. A replay that changes source data, transformation code, or model configuration creates a new idempotency key.
6. Recovery state is diagnostic and operational metadata; it must not contain secrets or sensitive personal data.

## Planned integration

The checkpoint writer is the foundation. Producer workflows will adopt checkpoints at their long-running boundaries, then the control plane will surface the latest successful checkpoint and whether a failed run is safely replayable.
