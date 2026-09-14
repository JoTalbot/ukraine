import hashlib
import json
from pathlib import Path

from scripts.check_production_readiness import check


def test_readiness_reports_missing_production_controls(tmp_path: Path) -> None:
    for path in ("README.md", "docs/ROADMAP.md", "docs/OBSERVABILITY.md", "docs/RECOVERY.md", "docs/SECURITY.md"):
        target = tmp_path / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text("ok", encoding="utf-8")
    scripts = tmp_path / "scripts"; scripts.mkdir()
    for name in ("write_recovery_checkpoint.py", "generate_release_manifest.py", "generate_sbom.py", "production_hardening.py"):
        (scripts / name).write_text("ok", encoding="utf-8")
    result = check(tmp_path)
    assert result["overall_state"] == "red"
    assert result["gates"]["dependency_lock"]["state"] == "red"
    assert result["gates"]["runtime_hardening_evidence"]["state"] == "red"
    assert result["gates"]["artifact_chain"]["state"] == "red"
    assert result["gates"]["promotion_policy"]["state"] == "red"


def _complete_tree(tmp_path: Path) -> None:
    for path in ("README.md", "docs/ROADMAP.md", "docs/OBSERVABILITY.md", "docs/RECOVERY.md", "docs/SECURITY.md", "docs/PRODUCTION_READINESS.md"):
        target = tmp_path / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text("ok", encoding="utf-8")
    scripts = tmp_path / "scripts"; scripts.mkdir()
    for name in ("write_recovery_checkpoint.py", "generate_release_manifest.py", "generate_sbom.py", "production_hardening.py"):
        (scripts / name).write_text("ok", encoding="utf-8")
    (tmp_path / "requirements-ci.lock").write_text("pytest==1.0\n", encoding="utf-8")


def _write_status_and_evidence(tmp_path: Path, source_commit: str = "abc123", freshness: object = None, authorization: bool = True, overall_state: str = "green") -> None:
    status = tmp_path / "artifacts/status/status-index.json"; status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps({"signals": {"ci": {}, "ingestion": {}, "quality": {}, "graph": {}, "training": {}, "publication": {}, "security": {}}, "policy": {"freshness_hours": {"ingestion": 48} if freshness is None else freshness}, "overall_state": overall_state}), encoding="utf-8")
    event = {"schema_version": 1, "event": "promote", "from": "candidate", "to": "production", "model_id": "m1", "artifact_sha256": "a" * 64, "evaluation_evidence_sha256": "b" * 64, "approval_identity": "test", "release_sequence": 1, "promoted_at": "2026-09-14T00:00:00+00:00"}
    evidence = tmp_path / "artifacts/status/production-hardening-evidence.json"
    evidence.write_text(json.dumps({"schema_version": 1, "state": "green", "source_commit": source_commit, "workflow_name": "test", "workflow_run_id": "42", "negative_tests": {"quarantine_tamper_rejected": True, "promotion_missing_metadata_rejected": True}, "contracts": {**{name: {"state": "green"} for name in ("DRIFT-01", "QUAR-01", "REG-01", "COMPAT-01", "ROLL-01")}, "PROM-01": {"state": "green", "promotion_event": event}}}), encoding="utf-8")
    artifact = tmp_path / "artifacts/model.bin"; evaluation = tmp_path / "artifacts/evaluation.json"
    artifact.write_bytes(b"production-model-fixture"); evaluation.write_text('{"score": 1}\n', encoding="utf-8")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest(); evaluation_sha = hashlib.sha256(evaluation.read_bytes()).hexdigest()
    manifest = tmp_path / "artifacts/status/release-manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "git_commit": source_commit, "files": [{"path": "README.md", "sha256": "a" * 64}]}), encoding="utf-8")
    (tmp_path / "artifacts/status/sbom.cdx.json").write_text("{}", encoding="utf-8")
    if authorization:
        auth = {"schema_version": 1, "target": "production", "source_commit": source_commit, "model_id": "m1", "artifact_sha256": artifact_sha, "evaluation_evidence_sha256": evaluation_sha, "artifact_path": "artifacts/model.bin", "evaluation_evidence_path": "artifacts/evaluation.json", "approval_identity": "approver", "release_sequence": 1, "approved_at": "2026-09-14T00:00:00+00:00"}
        (tmp_path / "artifacts/status/production-promotion-authorization.json").write_text(json.dumps(auth), encoding="utf-8")
    chain_artifacts = {p: {"sha256": "a" * 64, "bytes": 1} for p in ("artifacts/status/release-manifest.json", "artifacts/status/sbom.cdx.json", "artifacts/status/status-index.json", "artifacts/status/production-hardening-evidence.json")}
    if authorization: chain_artifacts["artifacts/status/production-promotion-authorization.json"] = {"sha256": "a" * 64, "bytes": 1}
    chain = tmp_path / "artifacts/status/artifact-chain.json"
    chain.write_text(json.dumps({"schema_version": 1, "state": "green", "source_commit": source_commit, "artifacts": chain_artifacts, "issues": []}), encoding="utf-8")


def test_readiness_accepts_complete_contract(tmp_path: Path) -> None:
    _complete_tree(tmp_path); _write_status_and_evidence(tmp_path)
    result = check(tmp_path)
    assert result["overall_state"] == "green"
    assert result["gates"]["control_plane"]["state"] == "green"
    assert result["gates"]["runtime_hardening_evidence"]["state"] == "green"
    assert result["gates"]["artifact_chain"]["state"] == "green"
    assert result["gates"]["promotion_policy"]["state"] == "green"


def test_readiness_rejects_red_control_plane_even_when_signals_are_complete(tmp_path: Path) -> None:
    _complete_tree(tmp_path); _write_status_and_evidence(tmp_path, overall_state="red")
    result = check(tmp_path)
    assert result["overall_state"] == "red"
    assert result["gates"]["control_plane"]["state"] == "red"
    assert result["gates"]["control_plane"]["overall_state"] == "red"


def test_readiness_rejects_missing_authoritative_authorization(tmp_path: Path) -> None:
    _complete_tree(tmp_path); _write_status_and_evidence(tmp_path, authorization=False)
    result = check(tmp_path)
    assert result["overall_state"] == "red"
    assert result["gates"]["promotion_policy"]["state"] == "red"
    assert result["gates"]["promotion_policy"]["authoritative_authorization_present"] is False


def test_readiness_rejects_evidence_for_different_release(tmp_path: Path) -> None:
    _complete_tree(tmp_path); _write_status_and_evidence(tmp_path, source_commit="evidence-commit")
    manifest = tmp_path / "artifacts/status/release-manifest.json"; payload = json.loads(manifest.read_text(encoding="utf-8")); payload["git_commit"] = "release-commit"; manifest.write_text(json.dumps(payload), encoding="utf-8")
    result = check(tmp_path)
    assert result["overall_state"] == "red"; assert result["gates"]["runtime_hardening_evidence"]["identity_matches_release"] is False


def test_readiness_rejects_empty_freshness_policy(tmp_path: Path) -> None:
    _complete_tree(tmp_path); _write_status_and_evidence(tmp_path, freshness={})
    result = check(tmp_path)
    assert result["overall_state"] == "red"; assert result["gates"]["control_plane"]["freshness_policy_present"] is False


def test_every_readiness_workflow_has_runtime_evidence_and_chain_before_gate() -> None:
    workflows = Path(__file__).parents[1] / ".github" / "workflows"; readiness_call = "python scripts/check_production_readiness.py"; evidence_call = "python scripts/production_hardening.py evidence"; chain_call = "python scripts/verify_artifact_chain.py"
    for workflow in sorted(workflows.glob("*.yml")):
        content = workflow.read_text(encoding="utf-8")
        if readiness_call not in content: continue
        assert evidence_call in content and chain_call in content, f"{workflow.name} is missing production evidence or artifact-chain verification"
        assert content.index(evidence_call) < content.index(chain_call) < content.index(readiness_call), f"{workflow.name} has invalid production-gate order"


def test_discovered_open_data_workflow_fails_after_persisting_batch_failures() -> None:
    workflow = Path(__file__).parents[1] / ".github" / "workflows" / "discovered-open-data-huggingface.yml"
    content = workflow.read_text(encoding="utf-8")
    persist = content.index("- name: Persist bootstrap progress"); fail = content.index("- name: Fail batch after persisting failure state"); publication = content.index("- name: Write publication status signal")
    assert persist < fail < publication
    assert "if: steps.batch.outputs.skip != 'true' && steps.assess.outputs.has_failures == 'true'" in content[fail:publication]
    assert "exit 1" in content[fail:publication]
