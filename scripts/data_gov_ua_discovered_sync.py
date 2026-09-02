#!/usr/bin/env python3
"""Mirror discovered data.gov.ua datasets to Hugging Face.

Downloads every discovered structured resource without artificial file-count or
size limits. The runner timeout and Hugging Face storage limits still apply.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, time
from pathlib import Path
import requests
from huggingface_hub import HfApi

CHUNK = 8 * 1024 * 1024
FETCH_ATTEMPTS = 4
HEADERS = {"User-Agent": "JoTalbot/ukraine-open-data-sync"}
STRUCTURED = {"CSV", "TSV", "JSON", "JSONL", "NDJSON", "XML", "XLS", "XLSX", "ODS", "PARQUET", "ZIP", "7Z", "GZ", "GZIP"}


def download_with_retries(url: str, dest: Path) -> int:
    """Stream a resource with retries on transient failures and 5xx replies."""
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with requests.get(url, stream=True, timeout=600, headers=HEADERS) as resp:
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"server replied {resp.status_code}", response=resp)
                resp.raise_for_status()
                total = 0
                with dest.open("wb") as f:
                    for chunk in resp.iter_content(CHUNK):
                        if chunk:
                            total += len(chunk)
                            f.write(chunk)
            return total
        except (requests.ConnectionError, requests.Timeout, requests.ChunkedEncodingError, requests.HTTPError) as exc:
            dest.unlink(missing_ok=True)  # never leave a truncated file behind
            if attempt == FETCH_ATTEMPTS:
                raise
            wait = min(2 ** attempt, 30)
            print(f"download attempt {attempt}/{FETCH_ATTEMPTS} failed for {url}: {exc!r}; retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def safe(s: str) -> str:
    return (re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ._-]+", "_", s or "resource")[:180] or "resource")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="artifacts/discovery/data_gov_ua_catalog.json")
    ap.add_argument("--max-dataset-files", type=int, default=0, help="0 = unlimited")
    ap.add_argument("--max-file-mb", type=int, default=0, help="0 = unlimited")
    ap.add_argument("--output", default="artifacts/discovered-open-data")
    args = ap.parse_args()
    token = os.environ.get("HF_TOKEN")
    repo = os.environ.get("HF_DATASET_REPO", "JoTalbot/ua-open-data")
    if not token: raise SystemExit("HF_TOKEN secret is missing")
    data = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    hf = HfApi(token=token)
    hf.create_repo(repo_id=repo, repo_type="dataset", exist_ok=True, private=False)
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    decisions = []
    for ds in data.get("datasets", []):
        ds_id = safe(ds.get("id") or ds.get("name"))
        resources = [r for r in ds.get("resources", []) if r.get("url") and r.get("format", "").upper() in STRUCTURED]
        if args.max_dataset_files > 0:
            resources = resources[:args.max_dataset_files]
        entry = {"id": ds_id, "name": ds.get("name"), "source_url": ds.get("url"), "modified": ds.get("modified"), "files": [], "skipped": []}
        for i, r in enumerate(resources):
            url = r["url"]
            dest = None
            try:
                name = safe(r.get("name") or Path(url.split("?")[0]).name or f"resource-{i}")
                if "." not in name: name += "." + r.get("format", "bin").lower()
                dest = root / ds_id / name; dest.parent.mkdir(parents=True, exist_ok=True)
                total = download_with_retries(url, dest)
                sha = file_sha256(dest)
                target = f"discovered/{ds_id}/{name}"
                hf.upload_file(path_or_fileobj=str(dest), path_in_repo=target, repo_id=repo, repo_type="dataset")
                entry["files"].append({"path":target,"sha256":sha,"bytes":total,"format":r.get("format")})
                print(f"Uploaded {target} ({total} bytes)")
            except Exception as exc:
                entry["skipped"].append({"url":url,"reason":str(exc)})
                print(f"Resource failed, continuing: {url}: {exc}")
            finally:
                if dest is not None:
                    try: dest.unlink(missing_ok=True)
                    except Exception: pass
        decisions.append(entry)
    manifest = root / "discovered-manifest.json"
    manifest.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    hf.upload_file(path_or_fileobj=str(manifest), path_in_repo="discovered-manifest.json", repo_id=repo, repo_type="dataset")
    print(f"Processed {len(decisions)} discovered datasets")

if __name__ == "__main__": main()
