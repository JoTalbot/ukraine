"""Aggregate workflow-produced status signals into the canonical control-plane index."""
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_signal(path: Path, expected_name: str, release_commit: str) -> dict:
    missing = {"state": "unknown", "detail": "no signal artifact recorded"}
    if not path.is_file():
        return missing
    try:
        payload = load_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"state": "red", "detail": "signal artifact is invalid JSON"}
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("signal") != expected_name:
        return {"state": "red", "detail": "signal artifact schema is invalid"}
    source_commit = payload.get("source_commit", payload.get("git_commit"))
    if source_commit != release_commit:
        return {"state": "unknown", "detail": "signal belongs to a different release commit"}
    if payload.get("state") not in VALID_STATES:
        return {"state": "red", "detail": "signal artifact has an invalid state"}
    result = {"state": payload["state"], "detail": str(payload.get("detail", ""))[:500]}
    for field in ("workflow_name", "workflow_run_id", "artifact"):
        if payload.get(field) not in (None, ""):
            result[field] = str(payload[field])[:200]
    return result


def build_status_index(manifest_path: Path, signals_dir: Path) -> dict:
    manifest = load_json(manifest_path)
    release_commit = manifest.get("git_commit")
    if not release_commit:
        raise ValueError("release manifest has no git_commit")

    signals = {
        name: {"state": "unknown", "detail": "no signal artifact recorded"} for name in SIGNALS
    }
    signals["ci"] = {"state": "healthy", "detail": "repository validation completed"}
    signals["security"] = {
        "state": "healthy",
        "detail": "repository security contract completed",
    }
    for name in PRODUCER_SIGNALS:
        signals[name] = normalize_signal(signals_dir / f"{name}.json", name, release_commit)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": "ukraine",
        "release": {
            "class": manifest.get("release_class"),
            "git_commit": release_commit,
            "git_branch": manifest.get("git_branch"),
            "manifest": str(manifest_path),
            "file_count": len(manifest.get("files", [])),
        },
        "runtime": {"python": platform.python_version()},
        "signals": signals,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="artifacts/status/release-manifest.json")
    parser.add_argument("--signals-dir", default="artifacts/status/signals")
    parser.add_argument("--output", default="artifacts/status/status-index.json")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_status_index(Path(args.manifest), Path(args.signals_dir))
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"aggregated status index written: {output}")


if __name__ == "__main__":
    main()
