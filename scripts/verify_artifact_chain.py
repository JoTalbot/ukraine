"""Verify the cryptographic binding of release-status artifacts.

The verifier intentionally avoids circular hashes: the release manifest is treated as
an input, while the chain binds the manifest itself plus generated SBOM, status index,
and runtime hardening evidence by their observed SHA-256 digests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

V = 1
REQUIRED = (
    "artifacts/status/release-manifest.json",
    "artifacts/status/sbom.cdx.json",
    "artifacts/status/status-index.json",
    "artifacts/status/production-hardening-evidence.json",
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root: Path, output: Path) -> int:
    root = Path(root)
    issues: list[str] = []
    files: dict[str, dict[str, str | int]] = {}
    for relative in REQUIRED:
        path = root / relative
        if not path.is_file():
            issues.append(f"missing artifact: {relative}")
            continue
        files[relative] = {"sha256": sha(path), "bytes": path.stat().st_size}

    manifest = None
    manifest_path = root / REQUIRED[0]
    if manifest_path.is_file():
        try:
            manifest = load(manifest_path)
            if manifest.get("schema_version") != V:
                issues.append("unsupported release manifest schema")
            if not manifest.get("git_commit"):
                issues.append("release manifest missing git_commit")
            if not isinstance(manifest.get("files"), list) or not manifest["files"]:
                issues.append("release manifest has no files")
            for entry in manifest.get("files", []):
                if not isinstance(entry, dict) or not entry.get("path") or not entry.get("sha256"):
                    issues.append("release manifest contains invalid file entry")
                    continue
                target = root / entry["path"]
                if not target.is_file():
                    issues.append(f"manifest file missing: {entry['path']}")
                    continue
                actual = sha(target)
                if actual != entry["sha256"]:
                    issues.append(f"manifest checksum mismatch: {entry['path']}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            issues.append("release manifest is invalid JSON")

    evidence_path = root / "artifacts/status/production-hardening-evidence.json"
    if evidence_path.is_file():
        try:
            evidence = load(evidence_path)
            if evidence.get("schema_version") != V:
                issues.append("unsupported hardening evidence schema")
            if manifest and evidence.get("source_commit") != manifest.get("git_commit"):
                issues.append("hardening evidence commit does not match release manifest")
            contracts = evidence.get("contracts", {})
            for name in ("DRIFT-01", "QUAR-01", "REG-01", "COMPAT-01", "PROM-01", "ROLL-01"):
                if contracts.get(name, {}).get("state") not in {"green", "quarantined"}:
                    issues.append(f"hardening contract not green: {name}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            issues.append("hardening evidence is invalid JSON")

    chain = {
        "schema_version": V,
        "state": "red" if issues else "green",
        "source_commit": manifest.get("git_commit") if manifest else None,
        "artifacts": files,
        "issues": issues,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(chain, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if issues else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="artifacts/status/artifact-chain.json")
    args = parser.parse_args()
    result = verify(Path(args.root), Path(args.output))
    print(json.dumps(load(Path(args.output)), ensure_ascii=False, indent=2))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
