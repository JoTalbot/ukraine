import json
from pathlib import Path

import pytest

from scripts.generate_replay_manifest import build_manifest, load_checkpoints


def checkpoint(tmp_path: Path, name: str, state: str, step: str, updated: str) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "checkpoint_id": name.replace(".json", "") + "0" * (64 - len(name.replace(".json", ""))),
                "workflow": "graph",
                "source_commit": "a" * 40,
                "idempotency_key": name,
                "checkpoint": step,
                "state": state,
                "updated_at_utc": updated,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_replay_manifest_resumes_from_incomplete_checkpoint(tmp_path: Path) -> None:
    first = checkpoint(tmp_path, "1", "succeeded", "build", "2026-09-03T10:00:00Z")
    second = checkpoint(tmp_path, "2", "failed", "publish", "2026-09-03T11:00:00Z")
    manifest = build_manifest(load_checkpoints([first, second]))
    assert manifest["next_action"] == "resume-from:publish"
    assert manifest["trusted_successful_checkpoints"] == ["build"]
    assert manifest["source_commit"] == "a" * 40
    assert len(manifest["manifest_sha256"]) == 64


def test_replay_manifest_is_complete_after_success(tmp_path: Path) -> None:
    path = checkpoint(tmp_path, "1", "succeeded", "publish", "2026-09-03T10:00:00Z")
    manifest = build_manifest(load_checkpoints([path]))
    assert manifest["next_action"] == "complete"


def test_replay_manifest_rejects_mixed_commits(tmp_path: Path) -> None:
    first = checkpoint(tmp_path, "1", "succeeded", "build", "2026-09-03T10:00:00Z")
    second = checkpoint(tmp_path, "2", "succeeded", "publish", "2026-09-03T11:00:00Z")
    data = json.loads(second.read_text(encoding="utf-8"))
    data["source_commit"] = "b" * 40
    second.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="multiple source commits"):
        load_checkpoints([first, second])


def test_replay_manifest_changes_only_when_replay_requested(tmp_path: Path) -> None:
    path = checkpoint(tmp_path, "1", "succeeded", "build", "2026-09-03T10:00:00Z")
    manifest = build_manifest(load_checkpoints([path]), replay_requested=True)
    assert manifest["next_action"] == "replay-from:build"
