"""Convert GitHub Actions job-step outcomes into deterministic recovery checkpoints."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKIP_NAMES = {"set up job", "complete job"}
SKIP_PREFIXES = ("post ",)
SLUG_RE = re.compile(r"[^a-z0-9]+")


def stage_slug(name: str) -> str:
    slug = SLUG_RE.sub("-", name.lower()).strip("-")
    return slug[:80] or "unnamed"


def stage_state(conclusion: str | None, status: str | None) -> str:
    value = (conclusion or status or "").lower()
    if value == "success":
        return "succeeded"
    if value in {"failure", "timed_out", "startup_failure", "action_required"}:
        return "failed"
    if value in {"cancelled", "skipped", "neutral", "stale"}:
        return "paused"
    return "running"


def extract_stages(jobs: list[dict]) -> list[dict]:
    stages: list[dict] = []
    sequence = 0
    for job in sorted(jobs, key=lambda item: (str(item.get("name", "")), int(item.get("id", 0)))):
        for step in sorted(job.get("steps") or [], key=lambda item: int(item.get("number", 0))):
            name = str(step.get("name", "")).strip()
            lowered = name.lower()
            if not name or lowered in SKIP_NAMES or lowered.startswith(SKIP_PREFIXES):
                continue
            sequence += 1
            stages.append(
                {
                    "sequence": sequence,
                    "job_id": int(job.get("id", 0)),
                    "job_name": str(job.get("name", "")),
                    "step_number": int(step.get("number", 0)),
                    "stage": f"stage-{sequence:03d}-{stage_slug(name)}",
                    "name": name,
                    "state": stage_state(step.get("conclusion"), step.get("status")),
                }
            )
    return stages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.jobs.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", payload) if isinstance(payload, dict) else payload
    if not isinstance(jobs, list) or not jobs:
        raise SystemExit("stage checkpoint extraction requires at least one job")

    stages = extract_stages(jobs)
    if not stages:
        raise SystemExit("stage checkpoint extraction found no stage steps")

    args.output.mkdir(parents=True, exist_ok=True)
    for stage in stages:
        key = f"workflow-run:{args.run_id}:job:{stage['job_id']}:stage:{stage['sequence']:03d}:{stage['stage']}"
        command = [
            "python", "scripts/write_recovery_checkpoint.py",
            "--workflow", args.workflow,
            "--source-commit", args.source_commit,
            "--idempotency-key", key,
            "--checkpoint", stage["stage"],
            "--state", stage["state"],
            "--detail", f"job {stage['job_id']} step {stage['step_number']}: {stage['name']} ({stage['state']})",
            "--output", str(args.output),
        ]
        # Keep this script a pure planner: the workflow invokes the existing writer
        # so the canonical checkpoint hashing and bounded-field rules stay central.
        import subprocess
        subprocess.run(command, check=True)

    print(f"stage checkpoints written: {len(stages)}")


if __name__ == "__main__":
    main()
