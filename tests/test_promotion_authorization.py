import hashlib
import json
from pathlib import Path

from scripts.verify_promotion_authorization import verify


def _auth(tmp_path: Path, artifact_path: str = "artifacts/model.bin", evaluation_path: str = "artifacts/evaluation.json") -> None:
    status = tmp_path / "artifacts/status"
    status.mkdir(parents=True)
    (status / "release-manifest.json").write_text(json.dumps({"schema_version": 1, "git_commit": "abc"}), encoding="utf-8")
    artifact = tmp_path / artifact_path
    evaluation = tmp_path / evaluation_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    evaluation.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"model")
    evaluation.write_text('{"score": 1}', encoding="utf-8")
    auth = {
        "schema_version": 1,
        "target": "production",
        "source_commit": "abc",
        "model_id": "m1",
        "artifact_path": artifact_path,
        "artifact_sha256": hashlib.sha256(b"model").hexdigest(),
        "evaluation_evidence_path": evaluation_path,
        "evaluation_evidence_sha256": hashlib.sha256(evaluation.read_bytes()).hexdigest(),
        "approval_identity": "approver",
        "release_sequence": 1,
        "approved_at": "2026-09-14T00:00:00+00:00",
    }
    (status / "production-promotion-authorization.json").write_text(json.dumps(auth), encoding="utf-8")


def test_authorization_requires_real_artifact_hashes(tmp_path: Path) -> None:
    _auth(tmp_path)
    ok, issues = verify(tmp_path)
    assert ok and issues == []
    (tmp_path / "artifacts/model.bin").write_bytes(b"tampered")
    ok, issues = verify(tmp_path)
    assert not ok and "production artifact checksum mismatch" in issues


def test_missing_authorization_fails_closed(tmp_path: Path) -> None:
    ok, issues = verify(tmp_path)
    assert not ok
    assert issues == ["missing authorization: artifacts/status/production-promotion-authorization.json"]


def test_unsafe_paths_fail_closed(tmp_path: Path) -> None:
    _auth(tmp_path)
    auth_path = tmp_path / "artifacts/status/production-promotion-authorization.json"
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["artifact_path"] = "../outside.bin"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    ok, issues = verify(tmp_path)
    assert not ok and "unsafe artifact_path" in issues

    auth["artifact_path"] = "/tmp/outside.bin"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    ok, issues = verify(tmp_path)
    assert not ok and "unsafe artifact_path" in issues

    auth["artifact_path"] = "artifacts/model.bin"
    auth["evaluation_evidence_path"] = "../evaluation.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    ok, issues = verify(tmp_path)
    assert not ok and "unsafe evaluation_evidence_path" in issues
