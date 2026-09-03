# Recovery and Replay

Long-running ingestion, graph, and training workflows must be recoverable without manually editing generated state.

## Checkpoint contract

`artifacts/recovery/checkpoints/<checkpoint_id>.json` is the machine-readable checkpoint format. The writer is `scripts/write_recovery_checkpoint.py`. Schema version 2 adds optional artifact provenance and checkpoint chaining.

Each checkpoint records:

- `workflow` — producer workflow identity.
- `source_commit` — exact repository revision being processed.
- `idempotency_key` — stable key for the logical run/input combination.
- `checkpoint` — completed stage, such as `download`, `normalize`, `build`, or `publish`.
- `state` — `running`, `succeeded`, `failed`, or `paused`.
- `checkpoint_id` — SHA-256 derived from workflow, source commit, and idempotency key.
- `previous_checkpoint` — optional predecessor identifier for an explicit replay chain.
- `artifact` — optional path, SHA-256, and byte count for the checkpoint output.
- bounded detail and UTC update time.

The derived checkpoint ID makes repeated writes for the same logical operation address the same state record. A retry must resume from the last trusted successful checkpoint rather than blindly repeating non-idempotent publication. Artifact hashes prevent a checkpoint from silently pointing at a changed output.

## Replay manifest contract

`artifacts/recovery/replay-manifest.json` is a deterministic replay plan generated from checkpoint records by `scripts/generate_replay_manifest.py`. It contains no wall-clock timestamp and is therefore safe to compare across repeated runs.

The manifest records the single source commit and workflow/run identity represented by the checkpoints, the ordered checkpoint chain, trusted successful checkpoints, referenced artifacts, and an explicit `next_action`. The generator rejects mixed source commits, malformed checkpoint identities, unsupported states, duplicate checkpoint IDs, and conflicting workflow identities.

`next_action` is deterministic:

- `resume-from:<checkpoint>` when a failed or paused checkpoint exists after the last trusted success;
- `replay-from:<checkpoint>` when only successful checkpoints exist and the caller explicitly requests replay planning;
- `complete` when the latest checkpoint succeeded and no later incomplete state exists.

The manifest is a plan, not an automatic authorization to republish. Publication remains behind the existing validation and model/data quality gates.

## Replay rules

1. Never treat a failed checkpoint as successful merely because an output file exists.
2. Reuse only artifacts whose source commit and input identity match the replay request.
3. Publication must remain behind the existing validation gates.
4. Retries must be safe to repeat. External uploads should use stable artifact paths or explicit revision metadata.
5. A replay that changes source data, transformation code, or model configuration creates a new idempotency key.
6. Recovery state is diagnostic and operational metadata; it must not contain secrets or sensitive personal data.

## Integration

Workflow-level durable completion checkpoints are integrated for core producer workflows. The deterministic replay-manifest primitive now provides a machine-readable bridge from those checkpoints to a safe resume/replay decision. Future producer-specific stage checkpoints can extend the chain without changing the contract.
