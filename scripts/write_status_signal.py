"""Write a safe producer status signal for the repository control plane."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SIGNALS = {"ingestion", "quality", "graph", "training", "publication", "security"}
STATES = {"green", "yellow", "red", "unknown"}


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal", required=True, choices=sorted(SIGNALS))
    parser.add_argument("--state", required=True, choices=sorted(STATES))
    parser.add_argument("--detail", required=True)
    parser.add_argument("--artifact", default="")
    parser.add_argument("--source-commit", default="")
    parser.add_argument("--workflow-name", default="")
    parser.add_argument("--workflow-run-id", default="")
    parser.add_argument("--output", default="artifacts/status/signals")
    args = parser.parse_args()

    if len(args.detail) > 500:
        raise SystemExit("status detail exceeds 500 characters")
    payload = {
        "schema_version": 1,
        "signal": args.signal,
        "state": args.state,
        "detail": args.detail,
        "source_commit": args.source_commit or git_commit(),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if args.workflow_name:
        payload["workflow_name"] = args.workflow_name
    if args.workflow_run_id:
        payload["workflow_run_id"] = args.workflow_run_id
    if args.artifact:
        payload["artifact"] = args.artifact

    output = Path(args.output) / f"{args.signal}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status signal written: {output}")


if __name__ == "__main__":
    main()
