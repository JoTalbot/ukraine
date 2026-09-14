import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.production_hardening import (
    compat,
    drift,
    evidence,
    promote,
    quarantine,
    registry,
    rollback,
    sha,
)


def write(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_drift_green_and_red(tmp_path):
    base = {"schema_version": 1, "schema_hash": "s", "row_count": 100, "field_distributions": {"a": {"x": 1}}, "source_available": True}
    write(tmp_path / "b.json", base); write(tmp_path / "c.json", base)
    assert drift(tmp_path / "b.json", tmp_path / "c.json", tmp_path / "r.json") == 0
    bad = dict(base); bad["row_count"] = 140; write(tmp_path / "c.json", bad)
    assert drift(tmp_path / "b.json", tmp_path / "c.json", tmp_path / "r.json") == 1


def test_registry_is_immutable(tmp_path):
    model = tmp_path / "model.bin"; model.write_bytes(b"model"); output = tmp_path / "registry.json"
    assert registry(model, "m1", "d1", "s1", output) == 0
    assert registry(model, "m1", "d1", "s1", output) == 0
    with pytest.raises(SystemExit): registry(model, "m1", "d2", "s1", output)


def test_compatibility(tmp_path):
    model_meta = tmp_path / "m.json"; dataset_meta = tmp_path / "d.json"; result = tmp_path / "r.json"
    write(model_meta, {"dataset_revision": "d1", "schema_hash": "s1"}); write(dataset_meta, {"revision": "d1", "schema_hash": "s1"})
    assert compat(model_meta, dataset_meta, result) == 0
    write(dataset_meta, {"revision": "d2", "schema_hash": "s1"})
    assert compat(model_meta, dataset_meta, result) == 1


def test_promotion_requires_authoritative_metadata(tmp_path):
    gates = tmp_path / "g.json"; output = tmp_path / "p.json"
    write(gates, {"compatibility": "green", "evaluation": "green", "readiness": "green"})
    assert promote("dev", "validated", gates, output) == 0
    assert promote("validated", "candidate", gates, output) == 0
    assert promote("candidate", "production", gates, output) == 1
    model_sha = "a" * 64; eval_sha = "b" * 64; timestamp = datetime.now(timezone.utc).isoformat()
    assert promote("candidate", "production", gates, output, model_id="m1", artifact_sha256=model_sha, evaluation_evidence_sha256=eval_sha, approval_identity="ci", release_sequence=1, promoted_at=timestamp) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["promotion_event"]["release_sequence"] == 1
    assert payload["promotion_event"]["artifact_sha256"] == model_sha


def test_promotion_requires_utc_timestamp(tmp_path):
    gates = tmp_path / "g.json"; output = tmp_path / "p.json"
    write(gates, {"compatibility": "green", "evaluation": "green", "readiness": "green"})
    common = {"model_id": "m1", "artifact_sha256": "a" * 64, "evaluation_evidence_sha256": "b" * 64, "approval_identity": "ci", "release_sequence": 1}
    assert promote("candidate", "production", gates, output, **common, promoted_at="2026-09-14T12:00:00") == 1
    assert promote("candidate", "production", gates, output, **common, promoted_at="2026-09-14T15:00:00+03:00") == 1
    assert promote("candidate", "production", gates, output, **common, promoted_at="2026-09-14T12:00:00Z") == 0


def test_quarantine_rejects_digest_mismatch(tmp_path):
    artifact = tmp_path / "artifact.bin"; artifact.write_bytes(b"good")
    out = tmp_path / "q.json"
    assert quarantine(artifact, tmp_path / "q", "test", "abc", "1", out) == 0
    target = tmp_path / "q" / f"artifact.bin.{sha(artifact)}"; target.write_bytes(b"tampered")
    with pytest.raises(SystemExit): quarantine(artifact, tmp_path / "q", "test", "abc", "1", out)


def test_rollback_requires_immutable_release_order(tmp_path):
    model = tmp_path / "model.bin"; model.write_bytes(b"model")
    registry_path = tmp_path / "registry.json"
    registry(model, "old", "d1", "s1", registry_path)
    data = json.loads(registry_path.read_text(encoding="utf-8")); ts = datetime.now(timezone.utc).isoformat()
    data["models"][0].update({"publication_state": "production", "release_sequence": 7, "promoted_at": ts})
    data["models"].append({**data["models"][0], "model_id": "current", "release_sequence": 8})
    registry_path.write_text(json.dumps(data), encoding="utf-8")
    assert rollback(registry_path, "current", tmp_path / "rollback.json") == 0
    result = json.loads((tmp_path / "rollback.json").read_text(encoding="utf-8"))
    assert result["rollback_target"]["model_id"] == "old"


def test_runtime_evidence_executes_all_contracts(tmp_path):
    output = tmp_path / "evidence.json"
    assert evidence(output, "abc123", "test-workflow", "42") == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["state"] == "green"
    assert payload["source_commit"] == "abc123"
    assert payload["workflow_run_id"] == "42"
    assert payload["negative_tests"]["quarantine_tamper_rejected"] is True
    assert payload["negative_tests"]["promotion_missing_metadata_rejected"] is True
    assert set(payload["contracts"]) == {"DRIFT-01", "QUAR-01", "REG-01", "COMPAT-01", "PROM-01", "ROLL-01"}
