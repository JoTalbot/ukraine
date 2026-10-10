# Production readiness audit — 2026-10-10

## Scope and evidence

Audit performed against `main` at source commit `7951c7dd2cec3c8f345df095d845e6e2aa833473`. This report records observations from GitHub Actions and tracked workflow/state files; it does not claim a complete release certification.

## Current evidence

- Ukraine data CI: run [38060752894](https://github.com/JoTalbot/ukraine/actions/runs/38060752894) completed successfully.
- Release Control Plane Dispatch: run [38060546000](https://github.com/JoTalbot/ukraine/actions/runs/38060546000) completed successfully.
- Open Data to Hugging Face mirror: run [38045763419](https://github.com/JoTalbot/ukraine/actions/runs/38045763419) completed successfully; the mirror, dataset-card, and publication-signal steps passed.
- Ukraine Open Data Discovery: run [38042801453](https://github.com/JoTalbot/ukraine/actions/runs/38042801453) completed successfully and discovered 500 datasets for its curated discovery artifact.
- The separate bootstrap state at `.github/state/discovered-open-data-progress.json` reports `completed_batches=4` of `batch_count=356`, `bootstrap_complete=false`, `blocked_batch_count=73`, `next_batch=175`, and last attempted batch 174 with 11 blocked resources. The file timestamp is 2026-10-10 09:05 UTC.
- The daily refresh workflow run [38045713346](https://github.com/JoTalbot/ukraine/actions/runs/38045713346) passed its bootstrap gate job but skipped both batch refresh and current-catalog discovery because bootstrap was incomplete. Therefore its green conclusion is not proof of a full refresh.
- Model training run [38043704092](https://github.com/JoTalbot/ukraine/actions/runs/38043704092) failed at the model quality gate: candidate validation loss 4.658300, published baseline 4.552100, allowed maximum 4.643142. The candidate is about 2.33% worse than the baseline, beyond the configured 2% tolerance. The gate behaved as configured and should not be weakened merely to make the workflow green.

## Release blockers

### P0 — Discovery/bootstrap not complete

The progress state records only 4 successful batches out of 356. 73 batches are currently blocked, and the recorded unavailable hosts include `data.dniprorada.gov.ua` and `opendata.gov.ua`. The 15-minute bootstrap workflow uses a single concurrency group, selects previously unseen batches before retrying failures, and records external source blocks separately from pipeline failures.

Actions:
1. Keep the distinction between source-unavailable blocks and actual pipeline errors.
2. Add a compact per-batch diagnostic artifact/report with source host, resource URL, failure class, attempt count, and retry eligibility, while avoiding secrets or personal data.
3. Improve retry scheduling so blocked hosts do not monopolize the retry queue; use bounded exponential backoff and host-level circuit breaking.
4. Recompute `bootstrap_complete` only from verified clean batches and validated artifacts.
5. Do not mark the data product production-certified until this state is closed or an explicit, auditable scope exception is approved.

### P0 — Model candidate rejected

The quality gate is operating correctly. The candidate exceeds the maximum permitted validation loss.

Actions:
1. Compare the candidate and published model's dataset revision, preprocessing, tokenizer, evaluation split, and metric-generation code before interpreting the comparison as a pure model regression.
2. Inspect the complete `metrics.jsonl` learning curve and training configuration; test whether more steps or a configuration change actually improves validation loss.
3. Keep publication blocked unless a comparable evaluation passes the existing threshold.
4. Publish the evaluation metadata and gate result as durable run artifacts for regression diagnosis.

### P1 — Release evidence

The CI and control-plane runs are green, but workflow success is not equivalent to full product readiness. Existing roadmap requirements for authoritative promotion evidence, cryptographic artifact binding, and operational atomic rollback must be verified against the exact release commit and real workflow execution.

Actions:
1. Confirm CHAIN-01 and PROM-02 runtime evidence is bound to the same source commit and release manifest.
2. Verify that promotion cannot occur without candidate artifact hashes and evaluation evidence.
3. Verify an actual atomic rollback against an immutable release sequence before declaring rollback production-ready.

## Definition of done

- Bootstrap state is complete for the declared catalog scope, with zero unresolved failed/blocked batches, or every excluded source is documented in an explicit approved exception.
- Model publication passes the quality gate on a comparable evaluation, or remains safely blocked.
- Release promotion, artifact binding, and rollback have verifiable runtime evidence for the exact release commit.
- The final readiness decision links to the relevant Actions runs, manifests, checksums, and evaluation artifacts.

## Limitations

This audit did not modify runtime behavior, rerun training, or certify the public Hugging Face artifacts end-to-end. The evidence above is a point-in-time snapshot, and the bootstrap state can change as scheduled workflows run.
