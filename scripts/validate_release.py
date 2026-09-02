"""Validate repository-level release metadata without touching source datasets."""
from __future__ import annotations

import json
import re
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REQUIRED_DOCS = (
    Path("README.md"),
    Path("docs/ROADMAP.md"),
    Path("docs/DATA_QUALITY.md"),
    Path("docs/REPRODUCIBILITY.md"),
    Path("docs/MODEL_EVALUATION.md"),
    Path("docs/OBSERVABILITY.md"),
    Path("docs/SECURITY.md"),
)


def validate_sha256(value: str) -> bool:
    """Return True only for a lowercase 64-character SHA-256 digest."""
    return bool(SHA256.fullmatch(value))


def validate_release_manifest(path: Path) -> list[str]:
    """Return manifest violations; an empty list means the manifest is valid."""
    if not path.is_file():
        return [f"missing release manifest: {path}"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"invalid release manifest JSON: {exc}"]

    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("release manifest schema_version must be 1")
    if manifest.get("release_class") != "repository":
        errors.append("release manifest release_class must be repository")
    if not isinstance(manifest.get("git_commit"), str) or not manifest["git_commit"]:
        errors.append("release manifest git_commit is missing")
    if not isinstance(manifest.get("git_branch"), str) or not manifest["git_branch"]:
        errors.append("release manifest git_branch is missing")
    if not isinstance(manifest.get("python"), str) or not manifest["python"]:
        errors.append("release manifest python is missing")
    timestamp = manifest.get("generated_at_utc")
    if not isinstance(timestamp, str) or not ISO_UTC.fullmatch(timestamp):
        errors.append("release manifest generated_at_utc must be UTC ISO-8601")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("release manifest files must be a non-empty list")
        return errors

    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"manifest file entry {index} is not an object")
            continue
        rel = item.get("path")
        digest = item.get("sha256")
        size = item.get("bytes")
        if not isinstance(rel, str) or not rel or rel in seen:
            errors.append(f"manifest file entry {index} has a missing or duplicate path")
        elif rel == "release-manifest.json" or rel.startswith(".git/"):
            errors.append(f"manifest file entry {index} contains an excluded path")
        else:
            seen.add(rel)
        if not isinstance(digest, str) or not validate_sha256(digest):
            errors.append(f"manifest file entry {index} has an invalid SHA-256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"manifest file entry {index} has an invalid byte size")
    return errors


def validate_repository_contract(root: Path = Path(".")) -> list[str]:
    """Return contract violations; an empty list means the contract passes."""
    errors = [f"missing required file: {p}" for p in REQUIRED_DOCS if not (root / p).is_file()]
    status_dir = root / "artifacts" / "status"
    if status_dir.exists() and not status_dir.is_dir():
        errors.append("artifacts/status exists but is not a directory")
    return errors


if __name__ == "__main__":
    violations = validate_repository_contract()
    manifest_path = Path("artifacts/status/release-manifest.json")
    if manifest_path.exists():
        violations.extend(validate_release_manifest(manifest_path))
    if violations:
        for violation in violations:
            print(f"ERROR: {violation}")
        raise SystemExit(1)
    print("Release contract OK")
