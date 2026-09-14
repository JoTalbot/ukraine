"""Evaluate deterministic production-readiness gates without mutating inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.verify_promotion_authorization import (
    verify as verify_promotion_authorization,
)

REQUIRED_DOCS = (
    "README.md", "docs/ROADMAP.md", "docs/OBSERVABILITY.md", "docs/RECOVERY.md",
    "docs/SECURITY.md", "docs/PRODUCTION_READINESS.md",
)
REQUIRED_SIGNALS = {"ci", "ingestion", "quality", "graph", "training", "publication", "security"}
HARDENING_CONTRACTS = {"DRIFT-01": "scripts/production_hardening.py", "QUAR-01": "scripts/production_hardening.py", "REG-01": "scripts/production_hardening.py", "COMPAT-01": "scripts/production_hardening.py", "PROM-01": "scripts/production_hardening.py", "ROLL-01": "scripts/production_hardening.py"}
PROMOTION_AUTHORIZATION = "artifacts/status/production-promotion-authorization.json"


def _valid_freshness_policy(policy: object) -> bool:
    return isinstance(policy, dict) and bool(policy) and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in policy.values())


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def check(root: Path) -> dict:
    gates = {}
    missing = [p for p in REQUIRED_DOCS if not (root / p).is_file()]
    gates["documentation"] = {"state": "green" if not missing else "red", "missing": missing}
    manifest = root / "artifacts/status/release-manifest.json"
    status = root / "artifacts/status/status-index.json"
    gates["release_manifest"] = {"state": "green" if manifest.is_file() else "red"}
    gates["status_index"] = {"state": "green" if status.is_file() else "red"}
    manifest_payload = None
    if manifest.is_file():
        try:
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            valid = manifest_payload.get("schema_version") == 1 and bool(manifest_payload.get("git_commit")) and isinstance(manifest_payload.get("files"), list) and bool(manifest_payload["files"])
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            valid = False
        gates["release_manifest"]["state"] = "green" if valid else "red"
        gates["release_manifest"]["identity_present"] = bool(manifest_payload and manifest_payload.get("git_commit"))
    if status.is_file():
        try:
            payload = json.loads(status.read_text(encoding="utf-8"))
            signals = set(payload.get("signals", {})); policy = payload.get("policy", {}).get("freshness_hours", {})
            complete = signals == REQUIRED_SIGNALS; freshness = _valid_freshness_policy(policy); overall_state = payload.get("overall_state", "unknown")
            gates["control_plane"] = {"state": "green" if complete and freshness and overall_state == "green" else "red", "signal_set_complete": complete, "freshness_policy_present": freshness, "overall_state": overall_state}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            gates["control_plane"] = {"state": "red", "detail": "status index is invalid JSON"}
    else:
        gates["control_plane"] = {"state": "red", "detail": "status index missing"}
    gates["recovery_contract"] = {"state": "green" if (root / "scripts/write_recovery_checkpoint.py").is_file() else "red"}
    lock = next((p for p in (root / "requirements.lock", root / "requirements-ci.lock", root / "uv.lock") if p.is_file()), None)
    gates["dependency_lock"] = {"state": "green" if lock else "red", "path": str(lock.relative_to(root)) if lock else None}
    gates["sbom"] = {"state": "green" if (root / "scripts/generate_sbom.py").is_file() else "red"}
    gates["provenance"] = {"state": "green" if (root / "scripts/generate_release_manifest.py").is_file() else "red"}
    for item, path in HARDENING_CONTRACTS.items():
        gates[item] = {"state": "green" if (root / path).is_file() else "red", "contract": path}

    evidence_path = root / "artifacts/status/production-hardening-evidence.json"
    if evidence_path.is_file():
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8")); contracts = evidence.get("contracts", {})
            identity_ok = bool(evidence.get("source_commit")) and bool(evidence.get("workflow_name")) and bool(evidence.get("workflow_run_id")) and evidence.get("schema_version") == 1
            identity_match = bool(manifest_payload) and evidence.get("source_commit") == manifest_payload.get("git_commit")
            contracts_ok = all(contracts.get(name, {}).get("state") in {"green", "quarantined"} for name in HARDENING_CONTRACTS)
            negative_ok = evidence.get("negative_tests", {}).get("quarantine_tamper_rejected") is True and evidence.get("negative_tests", {}).get("promotion_missing_metadata_rejected") is True
            gates["runtime_hardening_evidence"] = {"state": "green" if identity_ok and identity_match and contracts_ok and negative_ok else "red", "identity_present": identity_ok, "identity_matches_release": identity_match, "contracts_complete": contracts_ok, "negative_tests_complete": negative_ok}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            gates["runtime_hardening_evidence"] = {"state": "red", "detail": "hardening evidence is invalid JSON"}
    else:
        gates["runtime_hardening_evidence"] = {"state": "red", "detail": "runtime hardening evidence missing"}

    chain_path = root / "artifacts/status/artifact-chain.json"
    if chain_path.is_file():
        try:
            chain = json.loads(chain_path.read_text(encoding="utf-8")); chain_state = chain.get("state") == "green"
            chain_identity = bool(manifest_payload) and chain.get("source_commit") == manifest_payload.get("git_commit")
            artifact_set = set(chain.get("artifacts", {})); required_set = {"artifacts/status/release-manifest.json", "artifacts/status/sbom.cdx.json", "artifacts/status/status-index.json", "artifacts/status/production-hardening-evidence.json", PROMOTION_AUTHORIZATION}
            gates["artifact_chain"] = {"state": "green" if chain_state and chain_identity and artifact_set == required_set else "red", "identity_matches_release": chain_identity, "required_artifacts_bound": artifact_set == required_set}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            gates["artifact_chain"] = {"state": "red", "detail": "artifact chain is invalid JSON"}
    else:
        gates["artifact_chain"] = {"state": "red", "detail": "artifact chain missing"}

    authorization_path = root / PROMOTION_AUTHORIZATION; authorization = None
    if authorization_path.is_file():
        try:
            authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            authorization = None
    authorization_valid = (isinstance(authorization, dict) and authorization.get("schema_version") == 1 and authorization.get("target") == "production" and authorization.get("source_commit") == (manifest_payload.get("git_commit") if manifest_payload else None) and bool(authorization.get("model_id")) and _valid_sha(authorization.get("artifact_sha256")) and _valid_sha(authorization.get("evaluation_evidence_sha256")) and bool(authorization.get("approval_identity")) and isinstance(authorization.get("release_sequence"), int) and not isinstance(authorization.get("release_sequence"), bool) and authorization.get("release_sequence") > 0 and bool(authorization.get("approved_at")))
    verifier_ok, verifier_issues = verify_promotion_authorization(root)
    gates["promotion_policy"] = {"state": "green" if authorization_valid and verifier_ok else "red", "authoritative_authorization_present": authorization_valid, "real_artifact_binding_verified": verifier_ok, "verifier_issues": verifier_issues, "path": PROMOTION_AUTHORIZATION}

    states = [str(g.get("state", "red")) for g in gates.values()]
    overall = "red" if "red" in states else "yellow" if "yellow" in states else "green"
    return {"schema_version": 1, "overall_state": overall, "gates": gates}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("--output", default="artifacts/status/production-readiness.json"); args = parser.parse_args()
    result = check(Path(args.root)); output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"); print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["overall_state"] == "red": raise SystemExit(1)


if __name__ == "__main__": main()
