from __future__ import annotations

import json
from pathlib import Path

from scripts.check_model_quality import last_val_loss, main


def write_metrics(path: Path, values: list[float]) -> None:
    path.write_text(
        "".join(json.dumps({"step": i, "val_loss": value}) + "\n" for i, value in enumerate(values)),
        encoding="utf-8",
    )


def test_last_val_loss_returns_latest_value(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.jsonl"
    write_metrics(metrics, [0.9, 0.7, 0.6])
    assert last_val_loss(metrics) == 0.6


def test_initial_publication_passes(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.jsonl"
    output = tmp_path / "gate.json"
    write_metrics(candidate, [0.7])
    assert main(["--candidate", str(candidate), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["state"] == "green"


def test_regression_is_blocked(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.jsonl"
    baseline = tmp_path / "baseline.jsonl"
    write_metrics(candidate, [0.8])
    write_metrics(baseline, [0.7])
    assert main(
        ["--candidate", str(candidate), "--baseline", str(baseline), "--tolerance", "1.02"]
    ) == 1


def test_small_regression_within_tolerance_passes(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.jsonl"
    baseline = tmp_path / "baseline.jsonl"
    write_metrics(candidate, [0.71])
    write_metrics(baseline, [0.7])
    assert main(
        ["--candidate", str(candidate), "--baseline", str(baseline), "--tolerance", "1.02"]
    ) == 0
