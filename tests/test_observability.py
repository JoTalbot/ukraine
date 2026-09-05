from pathlib import Path


PRODUCER_SIGNAL_CONTRACT = {
    ".github/workflows/data-gov-discovery.yml": ("ingestion", "status-signal-ingestion"),
    ".github/workflows/ukraine-data-ci.yml": ("quality", "status-signal-quality"),
    ".github/workflows/entity-graph.yml": ("graph", "status-signal-graph"),
    ".github/workflows/kaggle-training.yml": ("training", "status-signal-training"),
    ".github/workflows/train-models.yml": ("training", "status-signal-training"),
    ".github/workflows/edrsr-huggingface.yml": ("publication", "status-signal-publication"),
    ".github/workflows/edrsr-texts.yml": ("publication", "status-signal-publication-edrsr-texts"),
    ".github/workflows/open-data-huggingface.yml": ("publication", "status-signal-publication-open-data"),
    ".github/workflows/discovered-open-data-huggingface.yml": (
        "publication",
        "status-signal-publication-discovered-open-data",
    ),
}


SUPPORT_WORKFLOWS = {
    ".github/workflows/failure-alerts.yml",
    ".github/workflows/kaggle-error-diagnostics.yml",
    ".github/workflows/kaggle-results-trigger.yml",
    ".github/workflows/kaggle-results.yml",
    ".github/workflows/pages-dashboard.yml",
    ".github/workflows/recovery-checkpoints.yml",
    ".github/workflows/release-control-plane.yml",
    ".github/workflows/release-observability.yml",
}


def test_every_operational_producer_has_standard_signal_contract() -> None:
    for relative, (signal, artifact_name) in PRODUCER_SIGNAL_CONTRACT.items():
        path = Path(__file__).parents[1] / relative
        assert path.is_file(), f"Missing producer workflow: {relative}"
        content = path.read_text(encoding="utf-8")
        assert "python scripts/write_status_signal.py" in content, relative
        assert f"--signal {signal}" in content, relative
        assert f"name: {artifact_name}" in content, relative
        assert "if: ${{ always() }}" in content, relative
        assert "--source-commit" in content, relative
        assert "--workflow-name" in content, relative
        assert "--workflow-run-id" in content, relative


def test_support_workflows_are_explicitly_excluded_from_producer_contract() -> None:
    workflows = Path(__file__).parents[1] / ".github" / "workflows"
    actual = {str(path.relative_to(workflows.parent.parent)) for path in workflows.glob("*.yml")}
    expected = set(PRODUCER_SIGNAL_CONTRACT) | SUPPORT_WORKFLOWS
    assert actual == expected
