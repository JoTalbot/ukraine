import json
from pathlib import Path

from scripts.generate_stage_checkpoints import extract_stages, stage_slug, stage_state
from scripts.generate_replay_manifest import build_manifest, load_checkpoints


def test_stage_slug_and_state_are_deterministic() -> None:
    assert stage_slug("Build Ukrainian legal corpus") == "build-ukrainian-legal-corpus"
    assert stage_state("success", "completed") == "succeeded"
    assert stage_state("failure", "completed") == "failed"
    assert stage_state("cancelled", "completed") == "paused"


def test_extract_stages_orders_jobs_and_steps_and_excludes_runner_bookends() -> None:
    jobs = [
        {
            "id": 20,
            "name": "train",
            "steps": [
                {"number": 2, "name": "Train model", "status": "completed", "conclusion": "success"},
                {"number": 1, "name": "Set up Python", "status": "completed", "conclusion": "success"},
                {"number": 3, "name": "Post cleanup", "status": "completed", "conclusion": "success"},
            ],
        },
        {
            "id": 10,
            "name": "build",
            "steps": [
                {"number": 1, "name": "Set up job", "status": "completed", "conclusion": "success"},
                {"number": 2, "name": "Download data", "status": "completed", "conclusion": "success"},
                {"number": 3, "name": "Build graph", "status": "completed", "conclusion": "failure"},
                {"number": 4, "name": "Complete job", "status": "completed", "conclusion": "success"},
            ],
        },
    ]
    stages = extract_stages(jobs)
    assert [stage["stage"] for stage in stages] == [
        "stage-001-download-data",
        "stage-002-build-graph",
        "stage-003-set-up-python",
        "stage-004-train-model",
    ]
    assert stages[1]["state"] == "failed"


def _checkpoint(tmp_path: Path, name: str, state: str, stage: str, updated: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({
        "schema_version": 2,
        "checkpoint_id": name + "0" * (64 - len(name)),
        "workflow": "train",
        "source_commit": "a" * 40,
        "idempotency_key": name,
        "checkpoint": stage,
        "state": state,
        "updated_at_utc": updated,
    }), encoding="utf-8")
    return path


def test_replay_manifest_identifies_last_trusted_stage_and_resume_boundary(tmp_path: Path) -> None:
    first = _checkpoint(tmp_path, "a", "succeeded", "stage-001-download", "2026-09-05T10:00:00Z")
    second = _checkpoint(tmp_path, "b", "succeeded", "stage-002-build", "2026-09-05T10:01:00Z")
    third = _checkpoint(tmp_path, "c", "failed", "stage-003-train", "2026-09-05T10:02:00Z")
    manifest = build_manifest(load_checkpoints([first, second, third]))
    assert manifest["trusted_successful_stages"] == ["stage-001-download", "stage-002-build"]
    assert manifest["last_trusted_stage"] == "stage-002-build"
    assert manifest["next_action"] == "resume-from:stage-003-train"


def test_recovery_workflow_requires_stage_checkpoint_generation_before_manifest() -> None:
    workflow = Path(__file__).parents[1] / ".github" / "workflows" / "recovery-checkpoints.yml"
    content = workflow.read_text(encoding="utf-8")
    assert "actions: read" in content
    assert "Fetch producer job steps" in content
    assert "scripts/generate_stage_checkpoints.py" in content
    assert content.index("scripts/generate_stage_checkpoints.py") < content.index("scripts/generate_replay_manifest.py")
    assert "trusted_successful_stages" in content
