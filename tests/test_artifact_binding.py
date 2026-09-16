from __future__ import annotations

import json
from pathlib import Path

from scripts.bind_release_artifacts import bind
from scripts.verify_artifact_chain import verify


def _manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_class": "repository",
                "git_commit": "a" * 40,
                "git_branch": "main",
                "generated_at_utc": "2026-09-16T12:00:00Z",
                "python": "3.12.0",
                "execution": {
                    "workflow_name": "test",
                    "workflow_run_id": "1",
                    "workflow_run_attempt": "1",
                    "event_name": "test",
                    "source_sha": "a" * 40,
                    "dependency_lock": {"path": "requirements.lock", "sha256": "b" * 64},
                },
                "files": [{"path": "README.md", "sha256": "c" * 64, "bytes": 1}],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _artifacts(root: Path) -> None:
    status = root / "artifacts/status"
    signals = status / "signals"
    signals.mkdir(parents=True)
    for name in ("sbom.cdx.json", "status-index.json", "production-hardening-evidence.json", "production-promotion-authorization.json"):
        (status / name).write_text(name, encoding="utf-8")
    for name in ("ingestion.json", "quality.json", "graph.json", "training.json", "publication.json", "security.json"):
        (signals / name).write_text(name, encoding="utf-8")


def test_bindings_cover_generated_artifacts_and_verify(tmp_path: Path) -> None:
    manifest = tmp_path / "artifacts/status/release-manifest.json"
    manifest.parent.mkdir(parents=True)
    _manifest(manifest)
    _artifacts(tmp_path)

    binding = bind(tmp_path, manifest)
    assert "artifacts/status/status-index.json" in binding["artifacts"]
    assert "artifacts/status/signals/training.json" in binding["artifacts"]

    output = tmp_path / "artifacts/status/artifact-chain.json"
    assert verify(tmp_path, output) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["state"] == "green"


def test_tampered_bound_artifact_fails_closed(tmp_path: Path) -> None:
    manifest = tmp_path / "artifacts/status/release-manifest.json"
    manifest.parent.mkdir(parents=True)
    _manifest(manifest)
    _artifacts(tmp_path)
    bind(tmp_path, manifest)

    (tmp_path / "artifacts/status/status-index.json").write_text("tampered", encoding="utf-8")
    output = tmp_path / "artifacts/status/artifact-chain.json"
    assert verify(tmp_path, output) == 1
    chain = json.loads(output.read_text(encoding="utf-8"))
    assert chain["state"] == "red"
    assert any("status-index.json" in issue for issue in chain["issues"])
