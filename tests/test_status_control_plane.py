from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.aggregate_status_signals import build_status_index, normalize_signal


def _manifest(path: Path, commit: str = "abc123") -> None:
    payload = {
        "git_commit": commit,
        "release_class": "data",
        "git_branch": "main",
        "files": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _signal(
    path: Path,
    state: str = "green",
    commit: str = "abc123",
    generated: datetime | None = None,
) -> None:
    payload = {
        "schema_version": 1,
        "signal": "security",
        "state": state,
        "detail": "SEC-01 result",
        "source_commit": commit,
        "generated_at_utc": (generated or datetime.now(timezone.utc)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "workflow_name": "Security scan",
        "workflow_run_id": "14",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_security_signal_is_consumed_and_preserves_state(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    _manifest(manifest)
    _signal(signals / "security.json", state="yellow")

    result = build_status_index(manifest, signals)

    assert result["signals"]["security"]["state"] == "yellow"
    assert result["overall_state"] == "yellow"


def test_missing_security_signal_is_unknown_not_green(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    _manifest(manifest)

    result = build_status_index(manifest, signals)

    assert result["signals"]["security"]["state"] == "unknown"


def test_security_signal_wrong_commit_is_unknown(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    signals = tmp_path / "signals"
    signals.mkdir()
    _manifest(manifest, commit="release-commit")
    _signal(signals / "security.json", commit="different-commit")

    result = build_status_index(manifest, signals)

    assert result["signals"]["security"]["state"] == "unknown"
    assert "different release commit" in result["signals"]["security"]["detail"]


def test_security_signal_stale_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "security.json"
    generated = datetime.now(timezone.utc) - timedelta(hours=49)
    _signal(path, generated=generated)

    result = normalize_signal(path, "security", "abc123")

    assert result["state"] == "unknown"
    assert "stale" in result["detail"]


def test_security_signal_invalid_schema_is_red(tmp_path: Path) -> None:
    path = tmp_path / "security.json"
    payload = {"schema_version": 99, "signal": "security", "state": "green"}
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_signal(path, "security", "abc123")

    assert result["state"] == "red"
