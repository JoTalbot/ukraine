"""Build a deterministic replay plan from recovery checkpoint JSON records."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATES = {"running", "succeeded", "failed", "paused"}
STAGE = re.compile(r"^stage-\d{3}-")


def load_checkpoints(paths: list[Path]) -> list[dict]:
    checkpoints: list[dict] = []
    seen: set[str] = set()
    for path in sorted(paths, key=lambda item: str(item)):
        data = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "schema_version",
            "checkpoint_id",
            "workflow",
            "source_commit",
            "idempotency_key",
            "checkpoint",
            "state",
        }
        missing = required - data.keys()
        if missing:
            raise ValueError(f"checkpoint {path} missing fields: {sorted(missing)}")
        if data["schema_version"] != 2:
            raise ValueError(f"checkpoint {path} schema_version must be 2")
        if not isinstance(data["checkpoint_id"], str) or len(data["checkpoint_id"]) != 64:
            raise ValueError(f"checkpoint {path} has invalid checkpoint_id")
        if not isinstance(data["source_commit"], str) or not SHA40.fullmatch(data["source_commit"]):
            raise ValueError(f"checkpoint {path} has invalid source_commit")
        if data["state"] not in STATES:
            raise ValueError(f"checkpoint {path} has invalid state")
        if data["checkpoint_id"] in seen:
            raise ValueError(f"duplicate checkpoint_id: {data['checkpoint_id']}")
        seen.add(data["checkpoint_id"])
        checkpoints.append(data)
    if not checkpoints:
        raise ValueError("no recovery checkpoints supplied")
    workflows = {item["workflow"] for item in checkpoints}
    commits = {item["source_commit"] for item in checkpoints}
    if len(workflows) != 1:
        raise ValueError("checkpoints contain multiple workflow identities")
    if len(commits) != 1:
        raise ValueError("checkpoints contain multiple source commits")
    return checkpoints


def sort_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get("updated_at_utc", "")),
        str(item["checkpoint"]),
        str(item["checkpoint_id"]),
    )


def build_manifest(checkpoints: list[dict], replay_requested: bool = False) -> dict:
    ordered = sorted(checkpoints, key=sort_key)
    trusted = [item for item in ordered if item["state"] == "succeeded"]
    incomplete = [item for item in ordered if item["state"] in {"failed", "paused", "running"}]
    stages = [item for item in ordered if STAGE.match(str(item["checkpoint"]))]
    trusted_stages = [item for item in stages if item["state"] == "succeeded"]
    incomplete_stages = [item for item in stages if item["state"] in {"failed", "paused", "running"}]

    if incomplete_stages:
        latest = incomplete_stages[-1]
        next_action = f"resume-from:{latest['checkpoint']}"
    elif incomplete:
        latest = incomplete[-1]
        next_action = f"resume-from:{latest['checkpoint']}"
    elif replay_requested:
        next_action = f"replay-from:{trusted[-1]['checkpoint']}" if trusted else "replay-from:start"
    else:
        next_action = "complete"

    artifacts = []
    for item in ordered:
        artifact = item.get("artifact")
        if isinstance(artifact, dict):
            artifacts.append(
                {
                    "checkpoint_id": item["checkpoint_id"],
                    "path": artifact.get("path", ""),
                    "sha256": artifact.get("sha256", ""),
                    "bytes": artifact.get("bytes", 0),
                }
            )

    chain = [
        {
            "checkpoint_id": item["checkpoint_id"],
            "checkpoint": item["checkpoint"],
            "state": item["state"],
            "idempotency_key": item["idempotency_key"],
            "previous_checkpoint": item.get("previous_checkpoint"),
        }
        for item in ordered
    ]
    payload = {
        "schema_version": 1,
        "workflow": ordered[0]["workflow"],
        "source_commit": ordered[0]["source_commit"],
        "checkpoint_count": len(ordered),
        "trusted_successful_checkpoints": [item["checkpoint"] for item in trusted],
        "trusted_successful_stages": [item["checkpoint"] for item in trusted_stages],
        "last_trusted_stage": trusted_stages[-1]["checkpoint"] if trusted_stages else None,
        "checkpoints": chain,
        "artifacts": artifacts,
        "next_action": next_action,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(load_checkpoints(args.input), replay_requested=args.replay)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"replay manifest failed: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"replay manifest written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
