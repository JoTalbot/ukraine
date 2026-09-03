"""Generate an auditable repository release manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_value(root: Path, *args: str) -> str:
    try:
        # Arguments are supplied only by this module's fixed internal calls.
        return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()  # noqa: S603
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def env_value(name: str) -> str:
    return os.environ.get(name, "unknown") or "unknown"


def build_manifest(root: Path) -> dict:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.name == "release-manifest.json":
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith("__pycache__/") or rel.endswith(".pyc"):
            continue
        files.append({"path": rel, "sha256": sha256(path), "bytes": path.stat().st_size})

    git_commit = git_value(root, "rev-parse", "HEAD")
    dependency_lock = root / "requirements.lock"
    execution = {
        "workflow_name": env_value("GITHUB_WORKFLOW"),
        "workflow_run_id": env_value("GITHUB_RUN_ID"),
        "workflow_run_attempt": env_value("GITHUB_RUN_ATTEMPT"),
        "event_name": env_value("GITHUB_EVENT_NAME"),
        "source_sha": git_commit,
        "dependency_lock": {
            "path": "requirements.lock",
            "sha256": sha256(dependency_lock) if dependency_lock.is_file() else "unknown",
        },
    }
    return {
        "schema_version": 1,
        "release_class": "repository",
        "git_commit": git_commit,
        "git_branch": git_value(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": platform.python_version(),
        "execution": execution,
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="artifacts/status/release-manifest.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(root)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Release manifest written: {output}")
    print(f"Tracked snapshot entries: {len(manifest['files'])}")


if __name__ == "__main__":
    main()
