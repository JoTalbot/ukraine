import json
from pathlib import Path

from scripts.generate_status_index import build_status_index


def test_status_index_links_release_identity(tmp_path: Path) -> None:
    status = tmp_path / "artifacts" / "status"
    status.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "release_class": "repository",
        "git_commit": "abc123",
        "git_branch": "main",
        "generated_at_utc": "2026-09-03T12:00:00Z",
        "python": "3.12.0",
        "files": [{"path": "README.md", "sha256": "0" * 64, "bytes": 5}],
    }
    (status / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    payload = build_status_index(tmp_path)

    assert payload["schema_version"] == 1
    assert payload["release"]["git_commit"] == "abc123"
    assert payload["release"]["manifest"] == "artifacts/status/release-manifest.json"
    assert payload["release"]["file_count"] == 1
    assert payload["signals"]["ci"]["state"] == "healthy"
    assert payload["signals"]["ingestion"]["state"] == "unknown"


def test_status_index_has_all_operational_signals(tmp_path: Path) -> None:
    status = tmp_path / "artifacts" / "status"
    status.mkdir(parents=True)
    (status / "release-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_class": "repository",
                "git_commit": "abc123",
                "git_branch": "main",
                "generated_at_utc": "2026-09-03T12:00:00Z",
                "python": "3.12.0",
                "files": [{"path": "README.md", "sha256": "0" * 64, "bytes": 5}],
            }
        ),
        encoding="utf-8",
    )

    payload = build_status_index(tmp_path)
    assert set(payload["signals"]) == {
        "ci",
        "ingestion",
        "quality",
        "graph",
        "training",
        "publication",
        "security",
    }
