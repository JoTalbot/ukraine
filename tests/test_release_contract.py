import hashlib
import json
from pathlib import Path

from scripts.validate_release import (
    validate_release_manifest,
    validate_repository_contract,
    validate_sha256,
    validate_status_index,
)


def execution() -> dict:
    return {
        "workflow_name": "CI",
        "workflow_run_id": "123",
        "workflow_run_attempt": "1",
        "event_name": "push",
        "source_sha": "abc123",
        "dependency_lock": {"path": "requirements.lock", "sha256": "0" * 64},
    }


def manifest_payload() -> dict:
    return {
        "schema_version": 1,
        "release_class": "repository",
        "git_commit": "abc123",
        "git_branch": "main",
        "generated_at_utc": "2026-09-03T12:00:00Z",
        "python": "3.12.0",
        "execution": execution(),
        "files": [{"path": "README.md", "sha256": "0" * 64, "bytes": 5}],
    }


def test_sha256_contract() -> None:
    assert validate_sha256("0" * 64)
    assert not validate_sha256("not-a-sha256")
    assert not validate_sha256("A" * 64)


def test_required_release_docs_exist() -> None:
    assert validate_repository_contract(Path(".")) == []


def test_release_manifest_contract_accepts_valid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    assert validate_release_manifest(path) == []


def test_release_manifest_contract_rejects_missing_execution(tmp_path: Path) -> None:
    manifest = manifest_payload()
    del manifest["execution"]
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = validate_release_manifest(path)
    assert any("execution metadata is missing" in error for error in errors)


def test_release_manifest_contract_rejects_duplicate_bad_entries(tmp_path: Path) -> None:
    manifest = manifest_payload()
    manifest["files"] = [
        {"path": "README.md", "sha256": "0" * 64, "bytes": 5},
        {"path": "README.md", "sha256": "bad", "bytes": -1},
        {"path": "release-manifest.json", "sha256": "0" * 64, "bytes": 1},
    ]
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = validate_release_manifest(path)
    assert any("duplicate path" in error for error in errors)
    assert any("invalid SHA-256" in error for error in errors)
    assert any("excluded path" in error for error in errors)
    assert any("invalid byte size" in error for error in errors)


def test_status_index_validates_sbom_checksum(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    status = tmp_path / "status-index.json"
    sbom = tmp_path / "sbom.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    manifest.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    status.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release": {"git_commit": "abc123"},
                "signals": {
                    "ci": {},
                    "ingestion": {},
                    "quality": {},
                    "graph": {},
                    "training": {},
                    "publication": {},
                    "security": {},
                },
                "supply_chain": {
                    "sbom": str(sbom),
                    "format": "CycloneDX",
                    "sha256": hashlib.sha256(sbom.read_bytes()).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    assert validate_status_index(status, manifest) == []
    sbom.write_text("tampered\n", encoding="utf-8")
    errors = validate_status_index(status, manifest)
    assert any("SBOM SHA-256" in error for error in errors)


def test_status_index_contract_requires_exact_release_identity(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    status = tmp_path / "status-index.json"
    manifest.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    status.write_text(json.dumps({"schema_version": 1, "release": {"git_commit": "different"}, "signals": {}}), encoding="utf-8")
    errors = validate_status_index(status, manifest)
    assert any("identity" in error for error in errors)
    assert any("signal set" in error for error in errors)
