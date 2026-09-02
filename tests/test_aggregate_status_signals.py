import json
from pathlib import Path

import pytest

from scripts.aggregate_status_signals import build_status_index


def write_manifest(path: Path, commit: str = "a" * 40) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_class": "repository",
                "git_commit": commit,
                "git_branch": "main",
                "files": [{"path": "README.md", "sha256": "b" * 64, "bytes": 1}],
            }
        ),
        encoding="utf-8",
    )


def write_signal(path: Path, **overrides: object) -> None:
    payload = {
        "schema_version": 1,
        "signal": "graph",
        "state": "green",
        "detail": "graph gate passed",
        "source_commit": "a" * 40,
        "workflow_name": "Entity graph",
        "workflow_run_id": 123,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_matching_signal_is_aggregated(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    write_manifest(manifest)
    write_signal(signals / "graph.json")

    index = build_status_index(manifest, signals)

    assert index["release"]["git_commit"] == "a" * 40
    assert index["signals"]["graph"]["state"] == "green"
    assert index["signals"]["graph"]["workflow_run_id"] == "123"


def test_stale_signal_becomes_unknown(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    write_manifest(manifest)
    write_signal(signals / "graph.json", source_commit="c" * 40)

    index = build_status_index(manifest, signals)

    assert index["signals"]["graph"]["state"] == "unknown"


def test_invalid_signal_becomes_red(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    write_manifest(manifest)
    (signals / "graph.json").write_text("not json", encoding="utf-8")

    index = build_status_index(manifest, signals)

    assert index["signals"]["graph"]["state"] == "red"


def test_missing_signal_is_unknown(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    write_manifest(manifest)

    index = build_status_index(manifest, signals)

    assert index["signals"]["training"]["state"] == "unknown"


def test_invalid_manifest_commit_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    write_manifest(manifest, commit="")

    with pytest.raises(ValueError, match="git_commit"):
        build_status_index(manifest, signals)
