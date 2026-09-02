import json
import subprocess
import sys
from pathlib import Path


def run_signal(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "scripts/write_status_signal.py", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_write_status_signal_creates_safe_payload(tmp_path: Path) -> None:
    output = tmp_path / "signals"
    result = run_signal(
        "--signal",
        "graph",
        "--state",
        "green",
        "--detail",
        "graph build completed",
        "--artifact",
        "graph_stats.json",
        "--source-commit",
        "a" * 40,
        "--workflow-name",
        "Entity graph",
        "--workflow-run-id",
        "123",
        "--output",
        str(output),
    )
    assert result.returncode == 0
    assert "status signal written" in result.stdout
    payload = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["signal"] == "graph"
    assert payload["state"] == "green"
    assert payload["artifact"] == "graph_stats.json"
    assert payload["source_commit"] == "a" * 40
    assert payload["workflow_name"] == "Entity graph"
    assert payload["workflow_run_id"] == "123"
    assert payload["generated_at_utc"].endswith("Z")


def test_write_status_signal_rejects_oversized_detail(tmp_path: Path) -> None:
    result = run_signal(
        "--signal",
        "quality",
        "--state",
        "green",
        "--detail",
        "x" * 501,
        "--output",
        str(tmp_path / "signals"),
    )
    assert result.returncode != 0
    assert "exceeds 500" in result.stderr
