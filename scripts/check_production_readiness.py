"""Evaluate deterministic production-readiness gates without mutating inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_DOCS = (
    "README.md",
    "docs/ROADMAP.md",
    "docs/OBSERVABILITY.md",
    "docs/RECOVERY.md",
    "docs/SECURITY.md",
    "docs/PRODUCTION_READINESS.md",
)
REQUIRED_SIGNALS = {
    "ci",
    "ingestion",
    "quality",
    "graph",
    "training",
    "publication",
    "security",
}
HARDENING_CONTRACTS = {
    "DRIFT-01": "scripts/production_hardening.py",
    "QUAR-01": "scripts/production_hardening.py",
    "REG-01": "scripts/production_hardening.py",
    "COMPAT-01": "scripts/production_hardening.py",
    "PROM-01": "scripts/production_hardening.py",
    "ROLL-01": "scripts/production_hardening.py",
}


def _valid_freshness_policy(policy: object) -> bool:
    """Require a non-empty mapping with positive numeric freshness windows."""
    if not isinstance(policy, dict) or not policy:
        return False
    for value in policy.values():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            return False
    return True


def check(root: Path) -> dict:
    """Return the deterministic readiness decision for a repository tree."""
    gates = {}
    missing = [path for path in REQUIRED_DOCS if not (root / path).is_file()]
    gates["documentation"] = {
        "state": "green" if not missing else "red",
        "missing": missing,
    }

    manifest = root / "artifacts/status/release-manifest.json"
    status = root / "artifacts/status/status-index.json"
    gates["release_manifest"] = {"state": "green" if manifest.is_file() else "red"}
    gates["status_index"] = {"state": "green" if status.is_file() else "red"}

    manifest_payload = None
    if manifest.is_file():
        try:
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_valid = (
                manifest_payload.get("schema_version") == 1
                and bool(manifest_payload.get("git_commit"))
                and isinstance(manifest_payload.get("files"), list)
                and bool(manifest_payload["files"])
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            manifest_valid = False
        gates["release_manifest"]["state"] = "green" if manifest_valid else "red"
        gates["release_manifest"]["identity_present"] = bool(
            manifest_payload and manifest_payload.get("git_commit")
        )

    if status.is_file():
        try:
            payload = json.loads(status.read_text(encoding="utf-8"))
            signals = set(payload.get("signals", {}))
            policy = payload.get("policy", {}).get("freshness_hours", {})
            complete = signals == REQUIRED_SIGNALS
            freshness = _valid_freshness_policy(policy)
            gates["control_plane"] = {
                "state": "green" if complete and freshness else "red",
                "signal_set_complete": complete,
                "freshness_policy_present": freshness,
                "overall_state": payload.get("overall_state", "unknown"),
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            gates["control_plane"] = {
                "state": "red",
                "detail": "status index is invalid JSON",
            }
    else:
        gates["control_plane"] = {"state": "red", "detail": "status index missing"}

    gates["recovery_contract"] = {
        "state": "green"
        if (root / "scripts/write_recovery_checkpoint.py").is_file()
        else "red"
    }
    lock = next(
        (
            path
            for path in (
                root / "requirements.lock",
                root / "requirements-ci.lock",
                root / "uv.lock",
            )
            if path.is_file()
        ),
        None,
    )
    gates["dependency_lock"] = {
        "state": "green" if lock else "red",
        "path": str(lock.relative_to(root)) if lock else None,
    }
    gates["sbom"] = {
        "state": "green"
        if (root / "scripts/generate_sbom.py").is_file()
        else "red"
    }
    gates["provenance"] = {
        "state": "green"
        if (root / "scripts/generate_release_manifest.py").is_file()
        else "red"
    }
    for item, path in HARDENING_CONTRACTS.items():
        gates[item] = {
            "state": "green" if (root / path).is_file() else "red",
            "contract": path,
        }

    evidence_path = root / "artifacts/status/production-hardening-evidence.json"
    if evidence_path.is_file():
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            contract_states = evidence.get("contracts", {})
            identity_ok = (
                bool(evidence.get("source_commit"))
                and bool(evidence.get("workflow_name"))
                and bool(evidence.get("workflow_run_id"))
                and evidence.get("schema_version") == 1
            )
            manifest_commit = manifest_payload.get("git_commit") if manifest_payload else None
            identity_match = bool(manifest_commit) and evidence.get("source_commit") == manifest_commit
            contracts_ok = all(
                contract_states.get(name, {}).get("state")
                in {"green", "quarantined"}
                for name in HARDENING_CONTRACTS
            )
            gates["runtime_hardening_evidence"] = {
                "state": "green" if identity_ok and identity_match and contracts_ok else "red",
                "identity_present": identity_ok,
                "identity_matches_release": identity_match,
                "contracts_complete": contracts_ok,
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            gates["runtime_hardening_evidence"] = {
                "state": "red",
                "detail": "hardening evidence is invalid JSON",
            }
    else:
        gates["runtime_hardening_evidence"] = {
            "state": "red",
            "detail": "runtime hardening evidence missing",
        }

    gates["promotion_policy"] = {
        "state": "green"
        if (root / "docs/PRODUCTION_READINESS.md").is_file()
        else "red"
    }

    states = [str(gate.get("state", "red")) for gate in gates.values()]
    overall = "red" if "red" in states else "yellow" if "yellow" in states else "green"
    return {"schema_version": 1, "overall_state": overall, "gates": gates}


def main() -> None:
    """Write readiness evidence and fail closed on a red decision."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--output", default="artifacts/status/production-readiness.json"
    )
    args = parser.parse_args()
    result = check(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["overall_state"] == "red":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
