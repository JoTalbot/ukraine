import json
from pathlib import Path

import pytest

from scripts.write_recovery_checkpoint import checkpoint_id, main


def test_checkpoint_id_is_stable() -> None:
    first = checkpoint_id("graph", "a" * 40, "2026-09-03")
    second = checkpoint_id("graph", "a" * 40, "2026-09-03")
    other = checkpoint_id("graph", "b" * 40, "2026-09-03")
    assert first == second
    assert first != other
    assert len(first) == 64


def test_checkpoint_writer_rejects_oversized_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "write_recovery_checkpoint.py",
            "--workflow", "graph",
            "--source-commit", "a" * 40,
            "--idempotency-key", "run-1",
            "--checkpoint", "publish",
            "--state", "failed",
            "--detail", "x" * 501,
        ],
    )
    with pytest.raises(SystemExit, match="exceeds 500"):
        main()


def test_checkpoint_writer_writes_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "write_recovery_checkpoint.py",
            "--workflow", "graph",
            "--source-commit", "a" * 40,
            "--idempotency-key", "run-1",
            "--checkpoint", "publish",
            "--state", "succeeded",
            "--detail", "published",
            "--output", str(tmp_path),
        ],
    )
    main()
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["state"] == "succeeded"
    assert payload["checkpoint"] == "publish"
    assert payload["checkpoint_id"] == checkpoint_id("graph", "a" * 40, "run-1")
