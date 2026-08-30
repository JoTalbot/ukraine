#!/usr/bin/env python3
"""Discover and mirror selected public Data.gov.ua datasets to Hugging Face.

The source is the official Ukrainian open-data portal CKAN API.
Only datasets explicitly enabled in config/ukraine_open_data_catalog.json are mirrored.
"""
import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.parse import quote

import requests
from huggingface_hub import HfApi

API = "https://data.gov.ua/api/3/action"
TIMEOUT = 60
CHUNK = 1024 * 1024


def api_get(action, params):
    r = requests.get(f"{API}/{action}", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"Data.gov.ua API error: {data.get('error')}")
    return data["result"]


def search_dataset(term):
    result = api_get("package_search", {"q": term, "rows": 10})
    if not result.get("results"):
        return None
    # Prefer an exact/near-exact title match and datasets with downloadable resources.
    terms = set(re.findall(r"[\wА-Яа-яІіЇїЄєҐґ]+", term.lower()))
    ranked = []
    for ds in result["results"]:
        title = ds.get("title", "")
        words = set(re.findall(r"[\wА-Яа-яІіЇїЄєҐґ]+", title.lower()))
        score = len(terms & words) * 10 + (20 if term.lower() in title.lower() else 0)
        score += min(len(ds.get("resources", [])), 5)
        ranked.append((score, ds))
    return max(ranked, key=lambda x: x[0])[1]


def safe_name(value):
    value = re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ._-]+", "_", value)
    return value[:180] or "resource"


def download(url, dest):
    with requests.get(url, stream=True, timeout=TIMEOUT, headers={"User-Agent": "JoTalbot/ukraine-open-data-sync"}) as r:
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            for chunk in r.iter_content(CHUNK):
                if chunk:
                    f.write(chunk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", help="catalog id, or all")
    ap.add_argument("--config", default="config/ukraine_open_data_catalog.json")
    ap.add_argument("--output", default="artifacts/open-data")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    repo = os.environ.get("HF_DATASET_REPO", "JoTalbot/ua-open-data")
    if not token:
        raise SystemExit("HF_TOKEN secret is missing")

    catalog = json.loads(Path(args.config).read_text(encoding="utf-8"))
    items = [x for x in catalog["datasets"] if x.get("enabled")]
    if args.dataset and args.dataset != "all":
        items = [x for x in items if x["id"] == args.dataset]
        if not items:
            raise SystemExit(f"Unknown or disabled dataset: {args.dataset}")

    hf = HfApi(token=token)
    hf.create_repo(repo_id=repo, repo_type="dataset", exist_ok=True, private=False)
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)

    manifest = []
    for item in sorted(items, key=lambda x: x.get("priority", 99)):
        if item["id"] == "edrsr":
            print("EDRSR is handled by the dedicated workflow; skipping")
            continue
        dataset = None
        for term in item.get("search_terms", []):
            try:
                dataset = search_dataset(term)
            except Exception as exc:
                print(f"Search failed for {item['id']}: {exc}")
        if not dataset:
            print(f"No dataset found: {item['id']}")
            continue

        ds_dir = root / item["id"]
        ds_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{item['id']}] {dataset.get('title')} -> {dataset.get('name')}")
        meta_path = ds_dir / "data.gov.ua.json"
        meta_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

        uploaded = []
        for resource in dataset.get("resources", []):
            url = resource.get("url")
            if not url or not url.startswith(("http://", "https://")):
                continue
            filename = safe_name(resource.get("name") or Path(url.split("?")[0]).name or resource.get("id", "resource"))
            if "." not in filename:
                fmt = resource.get("format", "bin").lower()
                filename += "." + safe_name(fmt)
            dest = ds_dir / filename
            try:
                print(f"Downloading {url}")
                download(url, dest)
                target = f"{item['id']}/{filename}"
                hf.upload_file(path_or_fileobj=str(dest), path_in_repo=target, repo_id=repo, repo_type="dataset")
                uploaded.append(target)
                print(f"Uploaded: {target}")
            except Exception as exc:
                print(f"Resource failed, continuing: {exc}")

        manifest.append({
            "catalog_id": item["id"],
            "title": dataset.get("title"),
            "source_url": dataset.get("url"),
            "metadata_modified": dataset.get("metadata_modified"),
            "uploaded_files": uploaded,
        })
        time.sleep(1)

    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    hf.upload_file(path_or_fileobj=str(manifest_path), path_in_repo="manifest.json", repo_id=repo, repo_type="dataset")
    print(f"Published {len(manifest)} datasets to {repo}")


if __name__ == "__main__":
    main()
