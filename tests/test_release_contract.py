import json
from pathlib import Path

from scripts.validate_release import (
    validate_release_manifest,
    validate_repository_contract,
    validate_sha256,
)


def test_sha256_contract() -> None:
    assert validate_sha256("0" * 64)
    assert not validate_sha256("not-a-sha256")
    assert not validate_sha256("A" * 64)


def test_required_release_docs_exist() -> None:
    assert validate_repository_contract(Path(".")) == []


def test_release_manifest_contract_accepts_valid_manifest(tmp_path: Path) -> None:
    manifest = {
        "schema_version": 1,
        "release_class": "repository",
        "git_commit": "abc123",
        "git_branch": "main",
        "generated_at_utc": "2026-09-03T12:00:00Z",
        "python": "3.12.0",
        "files": [{"path": "README.md", "sha256": "0" * 64, "bytes": 5}],
    }
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_release_manifest(path) == []


def test_release_manifest_contract_rejects_duplicate_bad_entries(tmp_path: Path) -> None:
    manifest = {
        "schema_version": 1,
        "release_class": "repository",
        "git_commit": "abc123",
        "git_branch": "main",
        "generated_at_utc": "2026-09-03T12:00:00Z",
        "python": "3.12.0",
        "files": [
            {"path": "README.md", "sha256": "0" * 64, "bytes": 5},
            {"path": "README.md", "sha256": "bad", "bytes": -1},
            {"path": "release-manifest.json", "sha256": "0" * 64, "bytes": 1},
        ],
    }
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = validate_release_manifest(path)
    assert any("duplicate path" in error for error in errors)
    assert any("invalid SHA-256" in error for error in errors)
    assert any("excluded path" in error for error in errors)
    assert any("invalid byte size" in error for error in errors)
