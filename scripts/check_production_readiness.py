"""Evaluate deterministic production-readiness gates without mutating generated state."""
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
)
REQUIRED_SIGNALS = {"ci", "ingestion", "quality", "graph", "training", "publication", "security"}


def check(root: Path) -> dict:
    gates: dict[str, dict[str, object]] = {}
    missing_docs = [p for p in REQUIRED_DOCS if not (root / p).is_file()]
    gates["documentation"] = {"state": "green" if not missing_docs else "red", "missing": missing_docs}

    manifest = root / "artifacts/status/release-manifest.json"
    status = root / "artifacts/status/status-index.json"
    gates["release_manifest"] = {"state": "green" if manifest.is_file() else "red"}
    gates["status_index"] = {"state": "green" if status.is_file() else "red"}

    if status.is_file():
        try:
            payload = json.loads(status.read_text(encoding="utf-8"))
            signals = set(payload.get("signals", {}))
            policy = payload.get("policy", {})
            gates["control_plane"] = {
                "state": "green" if signals == REQUIRED_SIGNALS and policy.get("freshness_hours") else "red",
                "signal_set_complete": signals == REQUIRED_SIGNALS,
                "freshness_policy_present": bool(policy.get("freshness_hours")),
                "overall_state": payload.get("overall_state", "unknown"),
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            gates["control_plane"] = {"state": "red", "detail": "status index is invalid JSON"}
    else:
        gates["control_plane"] = {"state": "red", "detail": "status index missing"}

    checkpoint = root / "scripts/write_recovery_checkpoint.py"
    gates["recovery_contract"] = {"state": "green" if checkpoint.is_file() else "red"}

    lock_candidates = (root / "requirements.lock", root / "requirements-ci.lock", root / "uv.lock")
    lock = next((p for p in lock_candidates if p.is_file()), None)
    gates["dependency_lock"] = {
        "state": "green" if lock else "red",
        "path": str(lock.relative_to(root)) if lock else None,
    }

    sbom = root / "scripts/generate_sbom.py"
    gates["sbom"] = {"state": "green" if sbom.is_file() else "red"}

    provenance = root / "scripts/generate_release_manifest.py"
    gates["provenance"] = {"state": "green" if provenance.is_file() else "red"}

    states = [str(gate.get("state", "red")) for gate in gates.values()]
    overall = "red" if "red" in states else "yellow" if "yellow" in states else "green"
    return {"schema_version": 1, "overall_state": overall, "gates": gates}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="artifacts/status/production-readiness.json")
    args = parser.parse_args()
    result = check(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["overall_state"] == "red":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
