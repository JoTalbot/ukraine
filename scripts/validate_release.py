"""Validate repository-level release metadata without touching source datasets."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REQUIRED_DOCS = (
    Path("README.md"), Path("docs/ROADMAP.md"), Path("docs/DATA_QUALITY.md"),
    Path("docs/REPRODUCIBILITY.md"), Path("docs/MODEL_EVALUATION.md"),
    Path("docs/OBSERVABILITY.md"), Path("docs/SECURITY.md"),
)
REQUIRED_SIGNALS = {"ci", "ingestion", "quality", "graph", "training", "publication", "security"}
REPRODUCIBLE_FIELDS = ("schema_version", "release_class", "git_commit", "git_branch", "python", "files")


def validate_sha256(value: str) -> bool:
    return bool(SHA256.fullmatch(value))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_release_manifest(path: Path) -> list[str]:
    if not path.is_file():
        return [f"missing release manifest: {path}"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"invalid release manifest JSON: {exc}"]
    errors: list[str] = []
    if manifest.get("schema_version") != 1: errors.append("release manifest schema_version must be 1")
    if manifest.get("release_class") != "repository": errors.append("release manifest release_class must be repository")
    if not isinstance(manifest.get("git_commit"), str) or not manifest["git_commit"]: errors.append("release manifest git_commit is missing")
    if not isinstance(manifest.get("git_branch"), str) or not manifest["git_branch"]: errors.append("release manifest git_branch is missing")
    if not isinstance(manifest.get("python"), str) or not manifest["python"]: errors.append("release manifest python is missing")
    timestamp = manifest.get("generated_at_utc")
    if not isinstance(timestamp, str) or not ISO_UTC.fullmatch(timestamp): errors.append("release manifest generated_at_utc must be UTC ISO-8601")

    execution = manifest.get("execution")
    if not isinstance(execution, dict):
        errors.append("release manifest execution metadata is missing")
    else:
        for field in ("workflow_name", "workflow_run_id", "workflow_run_attempt", "event_name", "source_sha"):
            if not isinstance(execution.get(field), str) or not execution[field]:
                errors.append(f"release manifest execution {field} is missing")
        if execution.get("source_sha") not in {manifest.get("git_commit"), "unknown"}:
            errors.append("release manifest execution source_sha does not match git_commit")
        lock = execution.get("dependency_lock")
        if not isinstance(lock, dict):
            errors.append("release manifest execution dependency_lock is missing")
        else:
            if lock.get("path") != "requirements.lock":
                errors.append("release manifest dependency lock path is invalid")
            lock_sha = lock.get("sha256")
            if not isinstance(lock_sha, str) or (lock_sha != "unknown" and not validate_sha256(lock_sha)):
                errors.append("release manifest dependency lock SHA-256 is invalid")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("release manifest files must be a non-empty list")
        return errors
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"manifest file entry {index} is not an object")
            continue
        rel, digest, size = item.get("path"), item.get("sha256"), item.get("bytes")
        if not isinstance(rel, str) or not rel: errors.append(f"manifest file entry {index} has a missing path")
        elif rel in seen: errors.append(f"manifest file entry {index} has a duplicate path")
        elif rel == "release-manifest.json" or rel.startswith(".git/"): errors.append(f"manifest file entry {index} contains an excluded path")
        else: seen.add(rel)
        if not isinstance(digest, str) or not validate_sha256(digest): errors.append(f"manifest file entry {index} has an invalid SHA-256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0: errors.append(f"manifest file entry {index} has an invalid byte size")
    return errors


def compare_release_manifests(first: Path, second: Path) -> list[str]:
    """Compare reproducibility-bearing fields while ignoring execution timestamps/identity."""
    errors: list[str] = []
    try:
        left, right = json.loads(first.read_text(encoding="utf-8")), json.loads(second.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"invalid manifest JSON for reproducibility comparison: {exc}"]
    errors.extend(f"first manifest: {error}" for error in validate_release_manifest(first))
    errors.extend(f"second manifest: {error}" for error in validate_release_manifest(second))
    if errors:
        return errors
    if left.get("git_commit") != right.get("git_commit"):
        return ["reproducibility comparison requires identical git_commit values"]
    for field in REPRODUCIBLE_FIELDS:
        if left.get(field) != right.get(field):
            errors.append(f"reproducibility drift in {field}")
    if left.get("generated_at_utc") == right.get("generated_at_utc"):
        errors.append("reproducibility comparison requires distinct generated_at_utc values")
    return errors


def validate_status_index(path: Path, manifest_path: Path) -> list[str]:
    if not path.is_file(): return [f"missing status index: {path}"]
    try:
        status = json.loads(path.read_text(encoding="utf-8")); manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"invalid status index JSON: {exc}"]
    errors: list[str] = []
    if status.get("schema_version") != 1: errors.append("status index schema_version must be 1")
    if status.get("release", {}).get("git_commit") != manifest.get("git_commit"): errors.append("status index release identity does not match manifest")
    if set(status.get("signals", {})) != REQUIRED_SIGNALS: errors.append("status index signal set is incomplete")
    supply_chain = status.get("supply_chain")
    if supply_chain is not None:
        if not isinstance(supply_chain, dict):
            errors.append("status index supply_chain must be an object")
        else:
            sbom_path = supply_chain.get("sbom")
            if supply_chain.get("format") != "CycloneDX":
                errors.append("status index SBOM format must be CycloneDX")
            if not isinstance(sbom_path, str) or not sbom_path:
                errors.append("status index SBOM path is missing")
            else:
                sbom = Path(sbom_path)
                if not sbom.is_file():
                    errors.append("status index SBOM file is missing")
                elif supply_chain.get("sha256") != file_sha256(sbom):
                    errors.append("status index SBOM SHA-256 does not match file")
    return errors


def validate_repository_contract(root: Path = Path(".")) -> list[str]:
    errors = [f"missing required file: {p}" for p in REQUIRED_DOCS if not (root / p).is_file()]
    status_dir = root / "artifacts" / "status"
    if status_dir.exists() and not status_dir.is_dir(): errors.append("artifacts/status exists but is not a directory")
    manifest = root / "artifacts/status/release-manifest.json"
    status = root / "artifacts/status/status-index.json"
    if manifest.is_file(): errors.extend(validate_release_manifest(manifest))
    if status.is_file() and manifest.is_file(): errors.extend(validate_status_index(status, manifest))
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare-manifests", nargs=2, metavar=("FIRST", "SECOND"))
    args = parser.parse_args()
    if args.compare_manifests:
        violations = compare_release_manifests(Path(args.compare_manifests[0]), Path(args.compare_manifests[1]))
        if violations:
            for violation in violations: print(f"ERROR: {violation}")
            raise SystemExit(1)
        print("Reproducibility comparison OK")
    else:
        violations = validate_repository_contract()
        if violations:
            for violation in violations: print(f"ERROR: {violation}")
            raise SystemExit(1)
        print("Release contract OK")
