# Recovery and Replay

Long-running ingestion, graph, and training workflows must be recoverable without manually editing generated state.

## Checkpoint contract

`artifacts/recovery/checkpoints/<checkpoint_id>.json` is the machine-readable checkpoint format. The writer is `scripts/write_recovery_checkpoint.py`. Schema version 2 adds optional artifact provenance and checkpoint chaining.

Each checkpoint records:

- `workflow` — producer workflow identity.
- `source_commit` — exact repository revision being processed.
- `idempotency_key` — stable key for the logical run/input combination.
- `checkpoint` — completed stage, such as `download`, `normalize`, `build`, or `publish`; stage-level checkpoints use the deterministic `stage-NNN-<slug>` form.
- `state` — `running`, `succeeded`, `failed`, or `paused`.
- `checkpoint_id` — SHA-256 derived from workflow, source commit, and idempotency key.
- `previous_checkpoint` — optional predecessor identifier for an explicit replay chain.
- `artifact` — optional path, SHA-256, and byte count for the checkpoint output.
- bounded detail and UTC update time.

The derived checkpoint ID makes repeated writes for the same logical operation address the same state record. Stage-level idempotency keys additionally include producer run, job, and deterministic stage sequence, so stages cannot overwrite one another. A retry must resume from the last trusted successful checkpoint rather than blindly repeating non-idempotent publication. Artifact hashes prevent a checkpoint from silently pointing at a changed output.

## Stage-level recovery

`Recovery Checkpoints` fetches the completed producer run's GitHub Actions job-step metadata and converts real step outcomes into stage checkpoints using `scripts/generate_stage_checkpoints.py`. Runner bookend steps such as `Set up job`, `Complete job`, and post-cleanup steps are excluded. Jobs and steps are ordered deterministically, and every retained stage receives a sequence-based checkpoint name.

The stage state is derived from the actual GitHub Actions outcome: successful steps are trusted, failures are failed checkpoints, and cancelled/skipped/unknown steps are non-trusted paused/running evidence. This creates an explicit resume boundary without depending on human interpretation of logs.

## Replay manifest contract

`artifacts/recovery/replay-manifest.json` is a deterministic replay plan generated from checkpoint records by `scripts/generate_replay_manifest.py`. It contains no wall-clock timestamp and is therefore safe to compare across repeated runs.

The manifest records the single source commit and workflow/run identity represented by the checkpoints, the ordered checkpoint chain, trusted successful checkpoints, trusted successful stages, the last trusted stage, referenced artifacts, and an explicit `next_action`. The generator rejects mixed source commits, malformed checkpoint identities, unsupported states, duplicate checkpoint IDs, and conflicting workflow identities.

`next_action` is deterministic:

- `resume-from:<checkpoint>` when a failed, paused, or running stage/checkpoint exists;
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
7. The last trusted stage is an execution boundary, not permission to skip validation or quality gates.

## Integration

Workflow-level durable completion checkpoints and stage-level checkpoints are integrated for the core producer workflows covered by `Recovery Checkpoints`. The deterministic replay-manifest primitive exposes the last trusted stage and safe resume boundary. Producer-specific stage names are derived from actual job steps, so new ingestion, graph, and training stages are covered without maintaining a second manually edited stage registry.
