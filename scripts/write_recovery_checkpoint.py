"""Write a bounded, machine-readable recovery checkpoint for long-running workflows."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

STATES = {"running", "succeeded", "failed", "paused"}
MAX_DETAIL = 500


def checkpoint_id(workflow: str, source_commit: str, key: str) -> str:
    raw = f"{workflow}\0{source_commit}\0{key}".encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--state", required=True, choices=sorted(STATES))
    parser.add_argument("--detail", default="")
    parser.add_argument("--output", default="artifacts/recovery/checkpoints")
    args = parser.parse_args()
    if len(args.detail) > MAX_DETAIL:
        raise SystemExit("recovery detail exceeds 500 characters")
    payload = {"schema_version": 1, "checkpoint_id": checkpoint_id(args.workflow, args.source_commit, args.idempotency_key), "workflow": args.workflow, "source_commit": args.source_commit, "idempotency_key": args.idempotency_key, "checkpoint": args.checkpoint, "state": args.state, "detail": args.detail, "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    output = Path(args.output) / f"{payload['checkpoint_id']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"recovery checkpoint written: {output}")


if __name__ == "__main__":
    main()
