from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.bind_release_artifacts import bind
from scripts.verify_artifact_chain import verify
from scripts.verify_promotion_authorization import authorization_id


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(path: Path) -> None:
    root = path.parents[2]
    readme = root / "README.md"
    readme.write_text("fixture", encoding="utf-8")
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
                "files": [{"path": "README.md", "sha256": _sha(readme), "bytes": readme.stat().st_size}],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _artifacts(root: Path) -> None:
    status = root / "artifacts/status"
    signals = status / "signals"
    signals.mkdir(parents=True)
    (status / "sbom.cdx.json").write_text("sbom", encoding="utf-8")
    (status / "status-index.json").write_text("status", encoding="utf-8")
    (status / "production-hardening-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_commit": "a" * 40,
                "contracts": {
                    name: {"state": "green"}
                    for name in ("DRIFT-01", "QUAR-01", "REG-01", "COMPAT-01", "PROM-01", "ROLL-01")
                },
            }
        ),
        encoding="utf-8",
    )
    authorization = {
        "schema_version": 1,
        "target": "production",
        "source_commit": "a" * 40,
        "model_id": "model-1",
        "artifact_sha256": "b" * 64,
        "evaluation_evidence_sha256": "c" * 64,
        "approval_identity": "test",
        "release_sequence": 1,
        "approved_at": "2026-09-16T12:00:00Z",
    }
    authorization["authorization_id"] = authorization_id(authorization)
    (status / "production-promotion-authorization.json").write_text(
        json.dumps(authorization), encoding="utf-8"
    )
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
