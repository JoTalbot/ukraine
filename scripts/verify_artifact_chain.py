"""Verify the cryptographic binding of release-status artifacts."""
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
    "artifacts/status/production-promotion-authorization.json",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest_bindings(root: Path, manifest: dict, issues: list[str]) -> None:
    bindings = manifest.get("artifact_bindings")
    if not isinstance(bindings, dict) or bindings.get("schema_version") != V:
        issues.append("release manifest artifact_bindings are missing or invalid")
        return
    artifacts = bindings.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        issues.append("release manifest artifact_bindings artifacts are empty")
        return
    for relative, expected in artifacts.items():
        path = root / relative
        if not path.is_file():
            issues.append(f"bound artifact missing: {relative}")
            continue
        if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
            issues.append(f"bound artifact checksum is invalid: {relative}")
            continue
        if sha(path) != expected["sha256"]:
            issues.append(f"bound artifact checksum mismatch: {relative}")
        if expected.get("bytes") != path.stat().st_size:
            issues.append(f"bound artifact byte-size mismatch: {relative}")


def verify_authorization_identity(root: Path, auth: dict, issues: list[str]) -> None:
    try:
        from scripts.verify_promotion_authorization import authorization_id
        expected = authorization_id(auth)
    except (ImportError, TypeError, ValueError):
        issues.append("unable to compute promotion authorization identity")
        return
    if not isinstance(auth.get("authorization_id"), str) or len(auth["authorization_id"]) != 64:
        issues.append("promotion authorization identity is missing or invalid")
    elif auth["authorization_id"] != expected:
        issues.append("promotion authorization identity checksum mismatch")


def verify(root: Path, output: Path) -> int:
    root = Path(root)
    issues: list[str] = []
    files: dict[str, dict[str, int | str]] = {}
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
                if sha(target) != entry["sha256"]:
                    issues.append(f"manifest checksum mismatch: {entry['path']}")
            verify_manifest_bindings(root, manifest, issues)
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

    authorization_path = root / "artifacts/status/production-promotion-authorization.json"
    if authorization_path.is_file():
        try:
            auth = load(authorization_path)
            if auth.get("schema_version") != V:
                issues.append("unsupported promotion authorization schema")
            if auth.get("target") != "production":
                issues.append("promotion authorization target is not production")
            if manifest and auth.get("source_commit") != manifest.get("git_commit"):
                issues.append("promotion authorization commit does not match release manifest")
            if not auth.get("model_id"):
                issues.append("promotion authorization missing model_id")
            for key in ("artifact_sha256", "evaluation_evidence_sha256"):
                if not isinstance(auth.get(key), str) or len(auth.get(key, "")) != 64:
                    issues.append(f"promotion authorization missing {key}")
            if not auth.get("approval_identity"):
                issues.append("promotion authorization missing approval_identity")
            if not isinstance(auth.get("release_sequence"), int) or isinstance(auth.get("release_sequence"), bool) or auth.get("release_sequence") <= 0:
                issues.append("promotion authorization requires positive release_sequence")
            if not auth.get("approved_at"):
                issues.append("promotion authorization missing approved_at")
            verify_authorization_identity(root, auth, issues)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            issues.append("promotion authorization is invalid JSON")

    chain = {
        "schema_version": V,
        "state": "red" if issues else "green",
        "source_commit": manifest.get("git_commit") if manifest else None,
        "artifacts": files,
        "issues": issues,
    }
    output = Path(output)
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
