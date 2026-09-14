import hashlib
import json
from pathlib import Path

from scripts.verify_promotion_authorization import verify


def test_authorization_requires_real_artifact_hashes(tmp_path: Path) -> None:
    status = tmp_path / "artifacts/status"
    status.mkdir(parents=True)
    (status / "release-manifest.json").write_text(json.dumps({"schema_version": 1, "git_commit": "abc"}), encoding="utf-8")
    artifact = tmp_path / "model.bin"
    evaluation = tmp_path / "evaluation.json"
    artifact.write_bytes(b"model")
    evaluation.write_text("{\"score\": 1}", encoding="utf-8")
    auth = {
        "schema_version": 1,
        "target": "production",
        "source_commit": "abc",
        "model_id": "m1",
        "artifact_path": "model.bin",
        "artifact_sha256": hashlib.sha256(b"model").hexdigest(),
        "evaluation_evidence_path": "evaluation.json",
        "evaluation_evidence_sha256": hashlib.sha256(evaluation.read_bytes()).hexdigest(),
        "approval_identity": "approver",
        "release_sequence": 1,
        "approved_at": "2026-09-14T00:00:00+00:00",
    }
    (status / "production-promotion-authorization.json").write_text(json.dumps(auth), encoding="utf-8")
    ok, issues = verify(tmp_path)
    assert ok and issues == []
    artifact.write_bytes(b"tampered")
    ok, issues = verify(tmp_path)
    assert not ok and "production artifact checksum mismatch" in issues


def test_missing_authorization_fails_closed(tmp_path: Path) -> None:
    ok, issues = verify(tmp_path)
    assert not ok
    assert issues == ["missing authorization: artifacts/status/production-promotion-authorization.json"]
