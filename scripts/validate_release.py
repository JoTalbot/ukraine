"""Validate repository-level release metadata without touching source datasets."""
from __future__ import annotations

import re
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
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


def validate_repository_contract(root: Path = Path(".")) -> list[str]:
    """Return contract violations; an empty list means the contract passes."""
    errors = [f"missing required file: {p}" for p in REQUIRED_DOCS if not (root / p).is_file()]
    status_dir = root / "artifacts" / "status"
    if status_dir.exists() and not status_dir.is_dir():
        errors.append("artifacts/status exists but is not a directory")
    return errors


if __name__ == "__main__":
    violations = validate_repository_contract()
    if violations:
        for violation in violations:
            print(f"ERROR: {violation}")
        raise SystemExit(1)
    print("Release contract OK")
