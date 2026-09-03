"""Deterministic contracts for DRIFT, QUAR, REG, COMPAT, PROM and ROLL."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path

V=1

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def dump(p, x):
    p=Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def sha(p):
    h=hashlib.sha256();
    with Path(p).open("rb") as f:
        for c in iter(lambda:f.read(1048576),b""): h.update(c)
    return h.hexdigest()

def drift(baseline,current,output,max_row_change=0.20):
    b,c=load(baseline),load(current); issues=[]
    if b.get("schema_version")!=V or c.get("schema_version")!=V: issues.append("unsupported schema")
    if b.get("schema_hash")!=c.get("schema_hash"): issues.append("schema_hash changed")
    br,cr=b.get("row_count"),c.get("row_count")
    if not isinstance(br,int) or not isinstance(cr,int) or br<0 or cr<0: issues.append("invalid row_count")
    elif br and abs(cr-br)/br>max_row_change: issues.append("row_count threshold exceeded")
    if b.get("field_distributions",{})!=c.get("field_distributions",{}): issues.append("field_distributions changed")
    if b.get("source_available") is not True or c.get("source_available") is not True: issues.append("source unavailable")
    dump(output,{"schema_version":V,"state":"red" if issues else "green","issues":issues,"max_row_change":max_row_change})
    return 1 if issues else 0

def quarantine(artifact,quarantine_dir,reason,source_commit,workflow_run_id,output):
    artifact=Path(artifact)
    if not artifact.is_file(): raise SystemExit(f"artifact not found: {artifact}")
    d=sha(artifact); target=Path(quarantine_dir)/(artifact.name+"."+d[:12]); target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(artifact,target)
    dump(output,{"schema_version":V,"state":"quarantined","artifact":str(target),"sha256":d,"reason":reason,"source_commit":source_commit,"workflow_run_id":workflow_run_id})
    return 0

def registry(model,model_id,dataset_revision,schema_hash,output,evaluation=None):
    model=Path(model)
    if not model.is_file(): raise SystemExit(f"model not found: {model}")
    rec={"schema_version":V,"model_id":model_id,"artifact":str(model),"artifact_sha256":sha(model),"dataset_revision":dataset_revision,"schema_hash":schema_hash,"evaluation":load(evaluation) if evaluation else {},"publication_state":"dev"}
    db=load(output) if Path(output).is_file() else {"schema_version":V,"models":[]}
    if db.get("schema_version")!=V: raise SystemExit("unsupported registry schema")
    for old in db.get("models",[]):
        if old.get("model_id")==model_id:
            if old!=rec: raise SystemExit("immutable model_id conflict")
            return 0
    db.setdefault("models",[]).append(rec); dump(output,db); return 0

def compat(model_meta,dataset_meta,output):
    m,d=load(model_meta),load(dataset_meta); issues=[]
    if m.get("dataset_revision")!=d.get("revision"): issues.append("dataset revision mismatch")
    if m.get("schema_hash")!=d.get("schema_hash"): issues.append("schema hash mismatch")
    dump(output,{"schema_version":V,"state":"red" if issues else "green","issues":issues}); return 1 if issues else 0

def promote(current_state,target_state,gates,output):
    allowed={"dev":{"validated"},"validated":{"candidate"},"candidate":{"production"},"production":set(),"rolled_back":{"validated"}}
    g=load(gates); issues=[]
    if target_state not in allowed.get(current_state,set()): issues.append("invalid promotion transition")
    if target_state in {"validated","candidate","production"} and g.get("compatibility")!="green": issues.append("compatibility gate not green")
    if target_state in {"candidate","production"} and g.get("evaluation")!="green": issues.append("evaluation gate not green")
    if target_state=="production" and g.get("readiness")!="green": issues.append("readiness gate not green")
    dump(output,{"schema_version":V,"from":current_state,"to":target_state,"state":"red" if issues else "green","issues":issues}); return 1 if issues else 0

def rollback(registry,current_model_id,output):
    db=load(registry); good=[m for m in db.get("models",[]) if m.get("publication_state")=="production" and m.get("model_id")!=current_model_id]; target=good[-1] if good else None
    dump(output,{"schema_version":V,"state":"green" if target else "red","current_model_id":current_model_id,"rollback_target":target,"action":"restore rollback_target atomically" if target else "no last-known-good production model"}); return 0 if target else 1

def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True)
    q=s.add_parser("drift"); q.add_argument("baseline"); q.add_argument("current"); q.add_argument("output"); q.add_argument("--max-row-change",type=float,default=.20)
    q=s.add_parser("quarantine"); q.add_argument("artifact"); q.add_argument("quarantine_dir"); q.add_argument("reason"); q.add_argument("source_commit"); q.add_argument("workflow_run_id"); q.add_argument("output")
    q=s.add_parser("registry"); q.add_argument("model"); q.add_argument("model_id"); q.add_argument("dataset_revision"); q.add_argument("schema_hash"); q.add_argument("output"); q.add_argument("--evaluation")
    q=s.add_parser("compat"); q.add_argument("model_meta"); q.add_argument("dataset_meta"); q.add_argument("output")
    q=s.add_parser("promote"); q.add_argument("current_state"); q.add_argument("target_state"); q.add_argument("gates"); q.add_argument("output")
    q=s.add_parser("rollback"); q.add_argument("registry"); q.add_argument("current_model_id"); q.add_argument("output")
    a=vars(p.parse_args()); cmd=a.pop("cmd"); raise SystemExit(globals()[cmd](**a))
if __name__=="__main__": main()
