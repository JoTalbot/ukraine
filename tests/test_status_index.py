import json
from pathlib import Path

from scripts.generate_status_index import build_status_index


def write_manifest(status: Path, commit: str = "abc123") -> None:
    (status / "release-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_class": "repository",
                "git_commit": commit,
                "git_branch": "main",
                "generated_at_utc": "2026-09-03T12:00:00Z",
                "python": "3.12.0",
                "files": [{"path": "README.md", "sha256": "0" * 64, "bytes": 5}],
            }
        ),
        encoding="utf-8",
    )


def status_index(status: Path) -> dict:
    return build_status_index(
        status / "release-manifest.json",
        status / "signals",
    )


def test_status_index_links_release_identity(tmp_path: Path) -> None:
    status = tmp_path / "artifacts" / "status"
    status.mkdir(parents=True)
    write_manifest(status)

    payload = status_index(status)

    assert payload["schema_version"] == 1
    assert payload["release"]["git_commit"] == "abc123"
    assert payload["release"]["manifest"] == "artifacts/status/release-manifest.json"
    assert payload["release"]["file_count"] == 1
    assert payload["signals"]["ci"]["state"] == "green"
    assert payload["signals"]["ingestion"]["state"] == "unknown"


def test_status_index_has_all_operational_signals(tmp_path: Path) -> None:
    status = tmp_path / "artifacts" / "status"
    status.mkdir(parents=True)
    write_manifest(status)

    payload = status_index(status)
    assert set(payload["signals"]) == {
        "ci",
        "ingestion",
        "quality",
        "graph",
        "training",
        "publication",
        "security",
    }


def test_status_index_consumes_matching_producer_signal(tmp_path: Path) -> None:
    status = tmp_path / "artifacts" / "status"
    signals = status / "signals"
    signals.mkdir(parents=True)
    write_manifest(status)
    (signals / "graph.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "signal": "graph",
                "state": "green",
                "detail": "graph build completed",
                "git_commit": "abc123",
                "generated_at_utc": "2026-09-03T12:00:00Z",
                "artifact": "graph_stats.json",
            }
        ),
        encoding="utf-8",
    )

    payload = status_index(status)
    graph = payload["signals"]["graph"]
    assert graph["state"] == "green"
    assert graph["detail"] == "graph build completed"
    assert graph["artifact"] == "graph_stats.json"
    assert graph["freshness_hours"] == 168


def test_status_index_rejects_signal_from_different_release(tmp_path: Path) -> None:
    status = tmp_path / "artifacts" / "status"
    signals = status / "signals"
    signals.mkdir(parents=True)
    write_manifest(status)
    (signals / "training.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "signal": "training",
                "state": "green",
                "detail": "training completed",
                "git_commit": "different-release",
                "generated_at_utc": "2026-09-03T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    payload = status_index(status)
    assert payload["signals"]["training"]["state"] == "unknown"
