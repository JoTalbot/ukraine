"""Bind generated release artifacts to the immutable release manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = 1
REQUIRED_ARTIFACTS = (
    Path("artifacts/status/sbom.cdx.json"),
    Path("artifacts/status/status-index.json"),
    Path("artifacts/status/production-hardening-evidence.json"),
)
OPTIONAL_ARTIFACTS = (Path("artifacts/status/production-promotion-authorization.json"),)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_artifacts(root: Path) -> list[Path]:
    artifacts = list(REQUIRED_ARTIFACTS)
    artifacts.extend(path for path in OPTIONAL_ARTIFACTS if (root / path).is_file())
    signal_dir = root / "artifacts/status/signals"
    if signal_dir.is_dir():
        artifacts.extend(sorted(p.relative_to(root) for p in signal_dir.glob("*.json") if p.is_file()))
    return artifacts


def bind(root: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported release manifest schema")
    if not manifest.get("git_commit"):
        raise ValueError("release manifest is missing git_commit")

    bindings: dict[str, dict[str, int | str]] = {}
    for relative in discover_artifacts(root):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"required release artifact is missing: {relative}")
        bindings[relative.as_posix()] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }

    manifest["artifact_bindings"] = {
        "schema_version": SCHEMA_VERSION,
        "artifacts": bindings,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest["artifact_bindings"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", default="artifacts/status/release-manifest.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest = root / args.manifest
    result = bind(root, manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
