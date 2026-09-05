import json
from pathlib import Path

from scripts.check_production_readiness import check


def test_readiness_reports_missing_production_controls(tmp_path: Path) -> None:
    for path in ("README.md", "docs/ROADMAP.md", "docs/OBSERVABILITY.md", "docs/RECOVERY.md", "docs/SECURITY.md"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/write_recovery_checkpoint.py").write_text("ok", encoding="utf-8")
    (tmp_path / "scripts/generate_release_manifest.py").write_text("ok", encoding="utf-8")
    (tmp_path / "scripts/generate_sbom.py").write_text("ok", encoding="utf-8")

    result = check(tmp_path)

    assert result["overall_state"] == "red"
    assert result["gates"]["dependency_lock"]["state"] == "red"
    assert result["gates"]["runtime_hardening_evidence"]["state"] == "red"


def test_readiness_accepts_complete_contract(tmp_path: Path) -> None:
    for path in ("README.md", "docs/ROADMAP.md", "docs/OBSERVABILITY.md", "docs/RECOVERY.md", "docs/SECURITY.md"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("write_recovery_checkpoint.py", "generate_release_manifest.py", "generate_sbom.py", "production_hardening.py"):
        (scripts / name).write_text("ok", encoding="utf-8")
    (tmp_path / "requirements-ci.lock").write_text("pytest==1.0\n", encoding="utf-8")
    status = tmp_path / "artifacts/status/status-index.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps({
        "signals": {"ci": {}, "ingestion": {}, "quality": {}, "graph": {}, "training": {}, "publication": {}, "security": {}},
        "policy": {"freshness_hours": {"ingestion": 48}},
        "overall_state": "green",
    }), encoding="utf-8")
    evidence = tmp_path / "artifacts/status/production-hardening-evidence.json"
    evidence.write_text(json.dumps({
        "schema_version": 1,
        "state": "green",
        "source_commit": "abc123",
        "workflow_name": "test",
        "workflow_run_id": "42",
        "contracts": {name: {"state": "green"} for name in ("DRIFT-01", "QUAR-01", "REG-01", "COMPAT-01", "PROM-01", "ROLL-01")},
    }), encoding="utf-8")

    result = check(tmp_path)

    assert result["gates"]["dependency_lock"]["state"] == "green"
    assert result["gates"]["control_plane"]["state"] == "green"
    assert result["gates"]["runtime_hardening_evidence"]["state"] == "green"


def test_every_readiness_workflow_has_runtime_evidence_before_gate() -> None:
    workflows = Path(__file__).parents[1] / ".github" / "workflows"
    readiness_call = "python scripts/check_production_readiness.py"
    evidence_call = "python scripts/production_hardening.py evidence"

    for workflow in sorted(workflows.glob("*.yml")):
        content = workflow.read_text(encoding="utf-8")
        if readiness_call not in content:
            continue
        assert evidence_call in content, f"{workflow.name} calls READY-01 without EVID-02 evidence"
        assert content.index(evidence_call) < content.index(readiness_call), (
            f"{workflow.name} evaluates READY-01 before generating EVID-02 evidence"
        )
