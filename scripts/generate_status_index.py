"""Build a safe machine-readable platform status index from local artifacts."""
from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
SIGNALS = ("ci", "ingestion", "quality", "graph", "training", "publication", "security")
PRODUCER_SIGNALS = set(SIGNALS) - {"ci", "security"}
VALID_STATES = {"green", "yellow", "red", "unknown"}


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_signal(status_dir: Path, name: str, release_commit: str) -> dict:
    path = status_dir / "signals" / f"{name}.json"
    if not path.is_file():
        return {"state": "unknown", "detail": "no signal artifact recorded"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"state": "red", "detail": "signal artifact is invalid JSON"}
    if payload.get("schema_version") != 1 or payload.get("signal") != name:
        return {"state": "red", "detail": "signal artifact schema is invalid"}
    if payload.get("git_commit") != release_commit:
        return {"state": "unknown", "detail": "signal belongs to a different release commit"}
    state = payload.get("state")
    if state not in VALID_STATES:
        return {"state": "red", "detail": "signal artifact has an invalid state"}
    result = {"state": state, "detail": str(payload.get("detail", ""))[:500]}
    if payload.get("artifact"):
        result["artifact"] = str(payload["artifact"])[:200]
    return result


def build_status_index(root: Path) -> dict:
    status_dir = root / "artifacts" / "status"
    manifest_path = status_dir / "release-manifest.json"
    manifest = load_manifest(manifest_path)
    release_commit = manifest.get("git_commit")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    signals = {
        name: {"state": "unknown", "detail": "no signal artifact recorded"} for name in SIGNALS
    }
    signals["ci"] = {
        "state": "healthy",
        "detail": "repository validation completed",
    }
    signals["security"] = {
        "state": "healthy",
        "detail": "repository security contract completed",
    }
    for name in PRODUCER_SIGNALS:
        signals[name] = load_signal(status_dir, name, release_commit)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "platform": "ukraine",
        "release": {
            "class": manifest.get("release_class"),
            "git_commit": release_commit,
            "git_branch": manifest.get("git_branch"),
            "manifest": "artifacts/status/release-manifest.json",
            "file_count": len(manifest.get("files", [])),
        },
        "runtime": {"python": platform.python_version()},
        "signals": signals,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="artifacts/status/status-index.json")
    args = parser.parse_args()
    root = Path(args.root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_status_index(root)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status index written: {output}")


if __name__ == "__main__":
    main()
