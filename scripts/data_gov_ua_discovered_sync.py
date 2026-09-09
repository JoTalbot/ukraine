#!/usr/bin/env python3
"""Mirror discovered data.gov.ua datasets to Hugging Face with incremental refresh."""
from __future__ import annotations
import argparse, contextlib, hashlib, json, os, re, time
from pathlib import Path
import requests
from huggingface_hub import HfApi
CHUNK=8*1024*1024; FETCH_ATTEMPTS=4; HEADERS={"User-Agent":"JoTalbot/ukraine-open-data-sync"}
STRUCTURED={"CSV","TSV","JSON","JSONL","NDJSON","XML","XLS","XLSX","ODS","PARQUET","ZIP","7Z","GZ","GZIP"}

def download_with_retries(url,dest):
    for attempt in range(1,FETCH_ATTEMPTS+1):
        try:
            with requests.get(url,stream=True,timeout=600,headers=HEADERS) as resp:
                if resp.status_code>=500: raise requests.HTTPError(f"server replied {resp.status_code}",response=resp)
                resp.raise_for_status(); total=0
                with dest.open("wb") as f:
                    for chunk in resp.iter_content(CHUNK):
                        if chunk: total+=len(chunk); f.write(chunk)
            return total
        except (requests.exceptions.ConnectionError,requests.exceptions.Timeout,requests.exceptions.ChunkedEncodingError,requests.exceptions.HTTPError) as exc:
            dest.unlink(missing_ok=True)
            if attempt==FETCH_ATTEMPTS: raise
            wait=min(2**attempt,30); print(f"download attempt {attempt}/{FETCH_ATTEMPTS} failed for {url}: {exc!r}; retrying in {wait}s"); time.sleep(wait)
    raise RuntimeError("unreachable")

def safe(s): return (re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ._-]+","_",s or "resource")[:180] or "resource")
def file_sha256(path):
    digest=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda:fh.read(CHUNK),b""): digest.update(chunk)
    return digest.hexdigest()
def resource_signature(r):
    return {"url":r.get("url"),"hash":r.get("hash"),"last_modified":r.get("last_modified"),"size":r.get("size")}
def same_resource(a,r):
    sig=resource_signature(r)
    if a.get("url")!=sig["url"]: return False
    if sig["hash"]: return a.get("source_hash")==sig["hash"]
    if sig["last_modified"] is not None or sig["size"] is not None:
        return a.get("source_last_modified")==sig["last_modified"] and a.get("source_size")==sig["size"]
    return False

def load_manifest(hf,repo,offset):
    try:
        path=hf.hf_hub_download(repo_id=repo,filename=f"batch-manifests/discovered-manifest-{offset}.json",repo_type="dataset",local_dir=".manifest-cache")
        return {x["source_url"]:x for x in json.loads(Path(path).read_text(encoding="utf-8"))}
    except Exception as exc:
        print(f"No prior manifest for batch offset {offset}: {exc}"); return {}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--catalog",default="artifacts/discovery/data_gov_ua_catalog.json"); ap.add_argument("--max-dataset-files",type=int,default=0); ap.add_argument("--max-file-mb",type=int,default=0); ap.add_argument("--dataset-offset",type=int,default=0); ap.add_argument("--dataset-limit",type=int,default=250); ap.add_argument("--output",default="artifacts/discovered-open-data"); ap.add_argument("--incremental",action="store_true"); args=ap.parse_args()
    if args.dataset_offset<0 or args.dataset_limit<0: raise SystemExit("dataset offset/limit must be >= 0")
    token=os.environ.get("HF_TOKEN"); repo=os.environ.get("HF_DATASET_REPO","JoTalbot/ua-open-data")
    if not token: raise SystemExit("HF_TOKEN secret is missing")
    all_datasets=json.loads(Path(args.catalog).read_text(encoding="utf-8")).get("datasets",[])
    datasets=all_datasets[args.dataset_offset:args.dataset_offset+args.dataset_limit] if args.dataset_limit else all_datasets[args.dataset_offset:]
    hf=HfApi(token=token); hf.create_repo(repo_id=repo,repo_type="dataset",exist_ok=True,private=False); root=Path(args.output); root.mkdir(parents=True,exist_ok=True)
    previous=load_manifest(hf,repo,args.dataset_offset) if args.incremental else {}; decisions=[]; failures=[]
    for ds in datasets:
        ds_id=safe(ds.get("id") or ds.get("name")); resources=[r for r in ds.get("resources",[]) if r.get("url") and r.get("format","").upper() in STRUCTURED]
        if args.max_dataset_files>0: resources=resources[:args.max_dataset_files]
        old=previous.get(ds.get("url"),{}); old_files={x.get("source_url"):x for x in old.get("files",[])}; entry={"id":ds_id,"name":ds.get("name"),"source_url":ds.get("url"),"modified":ds.get("modified"),"files":[],"failed":[]}
        for i,r in enumerate(resources):
            url=r["url"]; dest=None; prior=old_files.get(url)
            try:
                if args.incremental and prior and same_resource(prior,r):
                    entry["files"].append(prior); print(f"Unchanged, skipped download: {url}"); continue
                name=safe(r.get("name") or Path(url.split("?")[0]).name or f"resource-{i}"); name += "."+r.get("format","bin").lower() if "." not in name else ""; dest=root/ds_id/name; dest.parent.mkdir(parents=True,exist_ok=True)
                total=download_with_retries(url,dest)
                if args.max_file_mb>0 and total>args.max_file_mb*1024*1024: raise RuntimeError(f"resource exceeds --max-file-mb: {total} bytes")
                sha=file_sha256(dest); target=f"discovered/{ds_id}/{name}"; hf.upload_file(path_or_fileobj=str(dest),path_in_repo=target,repo_id=repo,repo_type="dataset")
                entry["files"].append({"path":target,"source_url":url,"source_hash":r.get("hash"),"source_last_modified":r.get("last_modified"),"source_size":r.get("size"),"sha256":sha,"bytes":total,"format":r.get("format")}); print(f"Uploaded {target} ({total} bytes)")
            except Exception as exc:
                failure={"url":url,"reason":str(exc)}; entry["failed"].append(failure); failures.append({"dataset":ds_id,**failure}); print(f"Resource failed: {url}: {exc}")
            finally:
                if dest is not None:
                    with contextlib.suppress(Exception): dest.unlink(missing_ok=True)
        decisions.append(entry)
    manifest=root/"discovered-manifest.json"; manifest.write_text(json.dumps(decisions,ensure_ascii=False,indent=2),encoding="utf-8"); hf.upload_file(path_or_fileobj=str(manifest),path_in_repo=f"batch-manifests/discovered-manifest-{args.dataset_offset}.json",repo_id=repo,repo_type="dataset")
    print(f"Processed {len(decisions)} discovered datasets; resource failures={len(failures)}")
    if failures: raise SystemExit(f"Batch incomplete: {len(failures)} resource(s) failed; progress must not advance")
if __name__=="__main__": main()
