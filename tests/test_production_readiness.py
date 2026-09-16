from pathlib import Path


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
    failure_gate = "if: steps.batch.outputs.skip != 'true' && steps.assess.outputs.failed_count != '0'"
    assert failure_gate in content[fail:publication]
    assert "exit 1" in content[fail:publication]


def test_discovered_open_data_scheduler_processes_unattempted_batches_before_retries() -> None:
    workflow = Path(__file__).parents[1] / ".github" / "workflows" / "discovered-open-data-huggingface.yml"
    content = workflow.read_text(encoding="utf-8")
    candidates = "candidates = [i for i in range(count) if i not in successful and i not in failed and i not in blocked]"
    assert candidates in content
    selection = content[content.index("else:", content.index("elif state.get('bootstrap_complete'")):content.index("offset = batch * size")]
    assert selection.index(candidates) < selection.index("elif failed:")
    assert "batch, mode = min(failed), 'retry'" in selection
