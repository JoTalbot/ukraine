import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.aggregate_status_signals import (
    build_status_index,
    normalize_signal,
    sha256,
)


def write_manifest(path: Path, commit: str = "a" * 40) -> None:
    path.write_text(json.dumps({"schema_version": 1, "release_class": "repository", "git_commit": commit, "git_branch": "main", "files": [{"path": "README.md", "sha256": "b" * 64, "bytes": 1}]}), encoding="utf-8")


def write_signal(path: Path, **overrides: object) -> None:
    payload = {"schema_version": 1, "signal": "graph", "state": "green", "detail": "graph gate passed", "source_commit": "a" * 40, "workflow_name": "Entity graph", "workflow_run_id": 123, "generated_at_utc": "2026-09-03T10:00:00Z"}
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
    assert index["signals"]["graph"]["freshness_hours"] == 168


def test_status_index_binds_sbom(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    sbom = tmp_path / "sbom.cdx.json"
    signals.mkdir()
    write_manifest(manifest)
    sbom.write_text('{"bomFormat":"CycloneDX","specVersion":"1.5"}\n', encoding="utf-8")
    index = build_status_index(manifest, signals, sbom)
    assert index["supply_chain"] == {"sbom": str(sbom), "format": "CycloneDX", "sha256": sha256(sbom)}


def test_status_index_rejects_missing_sbom(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    write_manifest(manifest)
    with pytest.raises(ValueError, match="SBOM path"):
        build_status_index(manifest, signals, tmp_path / "missing.json")


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
    assert index["overall_state"] == "green"


def test_invalid_manifest_commit_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    write_manifest(manifest, commit="")
    with pytest.raises(ValueError, match="git_commit"):
        build_status_index(manifest, signals)


def test_old_signal_is_stale() -> None:
    now = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
    payload = {"state": "green", "detail": "ok", "generated_at_utc": (now - timedelta(hours=169)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    result = normalize_signal_payload(payload, now)
    assert result["state"] == "unknown"


def normalize_signal_payload(payload: dict, now: datetime) -> dict:
    """Exercise freshness logic through the public normalizer using a temp file."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "graph.json"
        full = {"schema_version": 1, "signal": "graph", "source_commit": "a" * 40, **payload}
        path.write_text(json.dumps(full), encoding="utf-8")
        return normalize_signal(path, "graph", "a" * 40, now)
