#!/usr/bin/env python3
"""Discover public Ukrainian datasets through the data.gov.ua CKAN API."""
from __future__ import annotations

import argparse
import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://data.gov.ua/api/3/action/package_search"
PAGE_SIZE = 100
FETCH_ATTEMPTS = 5
# Ошибки, которые означают «источник недоступен/деградировал», а не «наш баг».
SOURCE_ERRORS = (
    http.client.HTTPException,
    urllib.error.HTTPError,
    urllib.error.URLError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
    ValueError,
    RuntimeError,
    OSError,
)


def fetch(q: str, rows: int = PAGE_SIZE, start: int = 0) -> dict:
    params = urllib.parse.urlencode({"q": q, "rows": rows, "start": start})
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "JoTalbot/ukraine-discovery"})
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (http.client.HTTPException, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == FETCH_ATTEMPTS:
                raise
            wait = min(2**attempt, 30)
            print(f"data.gov.ua fetch attempt {attempt}/{FETCH_ATTEMPTS} failed: {exc!r}; retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def discover(queries: list[str], limit: int) -> list[dict]:
    seen = {}
    for q in queries:
        start = 0
        while True:
            page = fetch(q, start=start)
            result = page.get("result", {})
            items = result.get("results", [])
            if not items:
                break
            for item in items:
                name = item.get("name") or item.get("id")
                if not name:
                    continue
                resources = []
                for res in item.get("resources", []):
                    url = res.get("url")
                    if url:
                        resources.append(
                            {
                                "name": clean(res.get("name")),
                                "format": clean(res.get("format")).upper(),
                                "url": url,
                                "hash": res.get("hash"),
                                "last_modified": res.get("last_modified"),
                                "size": res.get("size"),
                            }
                        )
                seen[item.get("id", name)] = {
                    "id": item.get("id", name),
                    "name": clean(item.get("title") or name),
                    "organization": clean((item.get("organization") or {}).get("title")),
                    "description": clean(item.get("notes")),
                    "url": f"https://data.gov.ua/dataset/{item.get('name', name)}",
                    "modified": item.get("metadata_modified"),
                    "resources": resources,
                }
            start += len(items)
            total = int(result.get("count") or 0)
            if start >= total or len(items) < PAGE_SIZE:
                break
    datasets = sorted(seen.values(), key=lambda x: (x["name"].lower(), x["id"]))
    return datasets if limit <= 0 else datasets[:limit]


def existing_datasets(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return -1
    items = data.get("datasets", data) if isinstance(data, dict) else data
    return len(items) if isinstance(items, list) else -1


def write_catalog_status(path: Path, *, refreshed: bool, datasets: int, detail: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "data.gov.ua",
        "refreshed": refreshed,
        "datasets": datasets,
        "detail": detail,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="artifacts/discovery/data_gov_ua_catalog.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--fallback-on-error",
        action="store_true",
        help="если CKAN API недоступен, не падать, а работать с уже существующим каталогом",
    )
    ap.add_argument("--status-output", default="artifacts/discovery/catalog-status.json")
    args = ap.parse_args()
    out = Path(args.output)
    try:
        datasets = discover(["Україна", "Ukraine", "відкриті дані", "державний реєстр"], args.limit)
    except SOURCE_ERRORS as exc:
        kept = existing_datasets(out)
        if not args.fallback_on_error or kept < 0:
            raise
        print(
            f"CATALOG DEGRADED: data.gov.ua API unavailable ({exc!r}); "
            f"keeping existing catalog with {kept} datasets"
        )
        print(f"Catalog status written: {write_catalog_status(Path(args.status_output), refreshed=False, datasets=kept, detail=str(exc))}")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"source": "data.gov.ua", "datasets": datasets}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_catalog_status(Path(args.status_output), refreshed=True, datasets=len(datasets), detail="CKAN package_search OK")
    print(f"Discovered {len(datasets)} datasets")


if __name__ == "__main__":
    main()
