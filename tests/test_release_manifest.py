from pathlib import Path

from scripts.generate_release_manifest import build_manifest, sha256


def test_release_manifest_has_audit_fields(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "requirements.lock").write_text("pytest==1.0\n", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    assert manifest["schema_version"] == 1
    assert manifest["release_class"] == "repository"
    assert manifest["python"]
    assert manifest["generated_at_utc"].endswith("Z")
    assert manifest["execution"]["source_sha"] == manifest["git_commit"]
    assert manifest["execution"]["dependency_lock"] == {
        "path": "requirements.lock",
        "sha256": sha256(tmp_path / "requirements.lock"),
    }
    assert manifest["files"] == [
        {"path": "README.md", "sha256": sha256(tmp_path / "README.md"), "bytes": 6},
        {"path": "requirements.lock", "sha256": sha256(tmp_path / "requirements.lock"), "bytes": 12},
    ]


def test_release_manifest_excludes_itself_and_git_metadata(tmp_path: Path) -> None:
    (tmp_path / "release-manifest.json").write_text("old\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret-ish metadata\n", encoding="utf-8")
    manifest = build_manifest(tmp_path)
    paths = {item["path"] for item in manifest["files"]}
    assert "release-manifest.json" not in paths
    assert ".git/config" not in paths
