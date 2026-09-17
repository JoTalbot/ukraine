"""Regression tests for direct-file script invocation, as CI calls them.

The suite mostly imports scripts as `from scripts.X import ...`, which works
under pytest because the repository root is on sys.path. CI instead runs
`python scripts/X.py`, where sys.path[0] becomes `scripts/` — so any script
that imports `scripts.*` needs its own repository-root bootstrap. These tests
exercise the CI invocation shape so that bootstrap cannot silently disappear.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
HARDENING_CONTRACTS = ("DRIFT-01", "QUAR-01", "REG-01", "COMPAT-01", "PROM-01", "ROLL-01")

# Scripts that import `scripts.*` at module level. If the bootstrap is dropped,
# the CI invocation dies with ModuleNotFoundError before any gate is evaluated.
CROSS_IMPORT_SCRIPTS = (
    "scripts/check_production_readiness.py",
    "scripts/generate_status_index.py",
    "scripts/verify_artifact_chain.py",
)


def run_script(
    script: str, *args: str, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / script), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_cross_importing_scripts_run_as_direct_files() -> None:
    """`python scripts/X.py --help` must not die on an unresolvable import."""
    for script in CROSS_IMPORT_SCRIPTS:
        result = run_script(script, "--help")
        assert result.returncode == 0, f"{script} is not runnable as a direct file:\n{result.stderr}"
        assert "ModuleNotFoundError" not in result.stderr, f"{script} lost its repository-root sys.path bootstrap"


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _authorization(root: Path, authorization_id: str) -> dict:
    artifact = root / "artifacts/model.bin"
    evaluation = root / "artifacts/evaluation.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"model")
    evaluation.write_text('{"score": 1}', encoding="utf-8")
    auth = {
        "schema_version": 1,
        "target": "production",
        "source_commit": COMMIT,
        "model_id": "m1",
        "artifact_path": "artifacts/model.bin",
        "artifact_sha256": hashlib.sha256(b"model").hexdigest(),
        "evaluation_evidence_path": "artifacts/evaluation.json",
        "evaluation_evidence_sha256": hashlib.sha256(evaluation.read_bytes()).hexdigest(),
        "approval_identity": "approver",
        "release_sequence": 1,
        "approved_at": "2026-09-14T00:00:00Z",
    }
    auth["authorization_id"] = authorization_id
    return auth


def _chain_fixture(tmp_path: Path, authorization_id: str) -> Path:
    """Build a complete artifact chain whose only defect is authorization_id."""
    status = tmp_path / "artifacts/status"
    status.mkdir(parents=True)
    (status / "sbom.cdx.json").write_text("{}", encoding="utf-8")
    (status / "status-index.json").write_text("{}", encoding="utf-8")
    _write(
        status / "production-hardening-evidence.json",
        {
            "schema_version": 1,
            "source_commit": COMMIT,
            "contracts": {name: {"state": "green"} for name in HARDENING_CONTRACTS},
        },
    )
    _write(status / "production-promotion-authorization.json", _authorization(tmp_path, authorization_id))

    # The manifest is written last so its digests describe the real files above.
    bound = {
        "artifacts/status/sbom.cdx.json",
        "artifacts/status/status-index.json",
        "artifacts/status/production-hardening-evidence.json",
        "artifacts/status/production-promotion-authorization.json",
    }
    tracked = "README.md"
    (tmp_path / tracked).write_text("fixture", encoding="utf-8")
    bindings = {
        relative: {
            "sha256": hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest(),
            "bytes": (tmp_path / relative).stat().st_size,
        }
        for relative in sorted(bound)
    }
    _write(
        status / "release-manifest.json",
        {
            "schema_version": 1,
            "release_class": "repository",
            "git_commit": COMMIT,
            "git_branch": "main",
            "files": [
                {
                    "path": tracked,
                    "sha256": hashlib.sha256((tmp_path / tracked).read_bytes()).hexdigest(),
                }
            ],
            "artifact_bindings": {"schema_version": 1, "artifacts": bindings},
        },
    )
    return status / "artifact-chain.json"


def test_artifact_chain_verifies_authorization_identity_when_run_as_direct_file(tmp_path: Path) -> None:
    """A wrong authorization_id must be reported as a checksum mismatch.

    Before the sys.path bootstrap, the direct-file invocation could not import
    `scripts.verify_promotion_authorization`; `verify_authorization_identity`
    swallowed the ImportError and reported the unrelated "unable to compute
    promotion authorization identity" instead of verifying anything.
    """
    output = _chain_fixture(tmp_path, authorization_id="0" * 64)
    result = run_script("scripts/verify_artifact_chain.py", "--root", str(tmp_path), "--output", str(output))
    assert result.returncode == 1
    chain = json.loads(output.read_text(encoding="utf-8"))
    assert "unable to compute promotion authorization identity" not in chain["issues"]
    assert "promotion authorization identity checksum mismatch" in chain["issues"]


def test_artifact_chain_accepts_canonical_authorization_identity(tmp_path: Path) -> None:
    """The same chain turns green once authorization_id is the canonical digest."""
    spec = _authorization(tmp_path, authorization_id="0" * 64)
    del spec["authorization_id"]
    canonical = hashlib.sha256(
        json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    ).hexdigest()

    # Re-create the fixture from scratch so the temp tree is not reused half-built.
    clean = tmp_path / "clean"
    clean.mkdir()
    output = _chain_fixture(clean, authorization_id=canonical)
    result = run_script("scripts/verify_artifact_chain.py", "--root", str(clean), "--output", str(output))
    assert result.returncode == 0, result.stdout + result.stderr
    chain = json.loads(output.read_text(encoding="utf-8"))
    assert chain["state"] == "green"
    assert chain["issues"] == []
    assert chain["source_commit"] == COMMIT


def _notebook(source: str) -> dict:
    return {
        "cells": [{"cell_type": "code", "source": source.splitlines(keepends=True)}],
        "nbformat": 4,
        "nbformat_minor": 4,
    }


GPU_MARKER = "!pip -q install tokenizers pyarrow huggingface_hub\n"


NOTEBOOK_NAMES = ("legal_lm_gpu.ipynb", "legal_lm_finetune.ipynb")


def test_patch_kaggle_notebooks_help_has_no_side_effects(tmp_path: Path) -> None:
    """`--help` must not rewrite notebooks before Python rejects the argument.

    The script patched `training/kaggle/` from a bare `__main__` loop with no
    argparse, so `python scripts/patch_kaggle_notebooks.py --help` silently
    mutated the working tree and only then failed on the unknown flag. The env
    override points the run at a scratch dir so a regression cannot touch the
    repository's real notebooks.
    """
    scratch = tmp_path / "nb"
    scratch.mkdir()
    gpu = scratch / "legal_lm_gpu.ipynb"
    gpu.write_text(json.dumps(_notebook(GPU_MARKER)), encoding="utf-8")
    before = gpu.read_bytes()

    result = run_script(
        "scripts/patch_kaggle_notebooks.py",
        "--help",
        env={"KAGGLE_NOTEBOOK_DIR": str(scratch)},
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert gpu.read_bytes() == before, "--help must not modify any notebook"


def test_patch_kaggle_notebooks_still_patches_with_no_arguments(tmp_path: Path) -> None:
    """The CI invocation (`python scripts/patch_kaggle_notebooks.py`) must still patch.

    Runs against a scratch dir and then asserts the repository's own notebooks
    are byte-identical to their pre-run state, so the assertion cannot be
    satisfied by mutating the checkout.
    """
    scratch = tmp_path / "nb"
    scratch.mkdir()
    gpu = scratch / "legal_lm_gpu.ipynb"
    gpu.write_text(json.dumps(_notebook(GPU_MARKER)), encoding="utf-8")

    before = {name: (ROOT / "training/kaggle" / name).read_bytes() for name in NOTEBOOK_NAMES}
    result = run_script(
        "scripts/patch_kaggle_notebooks.py",
        env={"KAGGLE_NOTEBOOK_DIR": str(scratch)},
    )
    assert result.returncode == 0, result.stderr
    for name, payload in before.items():
        assert (ROOT / "training/kaggle" / name).read_bytes() == payload, f"{name} was modified"

    patched = "".join(json.loads(gpu.read_text(encoding="utf-8"))["cells"][0]["source"])
    assert "uninstall -y torchvision" in patched


def test_production_readiness_fails_closed_when_run_as_direct_file(tmp_path: Path) -> None:
    """An empty root must produce a red gate report, not an import traceback."""
    output = tmp_path / "production-readiness.json"
    result = run_script(
        "scripts/check_production_readiness.py",
        "--root",
        str(tmp_path),
        "--output",
        str(output),
    )
    assert "ModuleNotFoundError" not in result.stderr
    assert result.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["overall_state"] == "red"
    assert report["gates"]["release_manifest"]["state"] == "red"
    assert report["gates"]["runtime_hardening_evidence"]["state"] == "red"
