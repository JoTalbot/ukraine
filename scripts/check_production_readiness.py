"""Evaluate deterministic production-readiness gates without mutating inputs."""
from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED_DOCS=("README.md","docs/ROADMAP.md","docs/OBSERVABILITY.md","docs/RECOVERY.md","docs/SECURITY.md","docs/PRODUCTION_READINESS.md")
REQUIRED_SIGNALS={"ci","ingestion","quality","graph","training","publication","security"}
HARDENING_CONTRACTS={
    "DRIFT-01":"scripts/production_hardening.py",
    "QUAR-01":"scripts/production_hardening.py",
    "REG-01":"scripts/production_hardening.py",
    "COMPAT-01":"scripts/production_hardening.py",
    "PROM-01":"scripts/production_hardening.py",
    "ROLL-01":"scripts/production_hardening.py",
}

def check(root:Path)->dict:
    gates={}
    missing=[p for p in REQUIRED_DOCS if not (root/p).is_file()]
    gates["documentation"]={"state":"green" if not missing else "red","missing":missing}
    manifest=root/"artifacts/status/release-manifest.json"; status=root/"artifacts/status/status-index.json"
    gates["release_manifest"]={"state":"green" if manifest.is_file() else "red"}
    gates["status_index"]={"state":"green" if status.is_file() else "red"}
    if status.is_file():
        try:
            payload=json.loads(status.read_text(encoding="utf-8")); signals=set(payload.get("signals",{})); policy=payload.get("policy",{})
            gates["control_plane"]={"state":"green" if signals==REQUIRED_SIGNALS and policy.get("freshness_hours") else "red","signal_set_complete":signals==REQUIRED_SIGNALS,"freshness_policy_present":bool(policy.get("freshness_hours")),"overall_state":payload.get("overall_state","unknown")}
        except (OSError,UnicodeDecodeError,json.JSONDecodeError): gates["control_plane"]={"state":"red","detail":"status index is invalid JSON"}
    else: gates["control_plane"]={"state":"red","detail":"status index missing"}
    gates["recovery_contract"]={"state":"green" if (root/"scripts/write_recovery_checkpoint.py").is_file() else "red"}
    lock=next((p for p in (root/"requirements.lock",root/"requirements-ci.lock",root/"uv.lock") if p.is_file()),None)
    gates["dependency_lock"]={"state":"green" if lock else "red","path":str(lock.relative_to(root)) if lock else None}
    gates["sbom"]={"state":"green" if (root/"scripts/generate_sbom.py").is_file() else "red"}
    gates["provenance"]={"state":"green" if (root/"scripts/generate_release_manifest.py").is_file() else "red"}
    for item,path in HARDENING_CONTRACTS.items(): gates[item]={"state":"green" if (root/path).is_file() else "red","contract":path}
    gates["promotion_policy"]={"state":"green" if (root/"docs/PRODUCTION_READINESS.md").is_file() else "red"}
    states=[str(g.get("state","red")) for g in gates.values()]
    overall="red" if "red" in states else "yellow" if "yellow" in states else "green"
    return {"schema_version":1,"overall_state":overall,"gates":gates}

def main()->None:
    p=argparse.ArgumentParser(); p.add_argument("--root",default="."); p.add_argument("--output",default="artifacts/status/production-readiness.json"); a=p.parse_args()
    result=check(Path(a.root)); out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False,indent=2));
    if result["overall_state"]=="red": raise SystemExit(1)
if __name__=="__main__": main()
