#!/usr/bin/env python3
"""Discover public Ukrainian datasets through the data.gov.ua CKAN API.

The API is paged so discovery is not artificially capped at the first 100
results. The final catalog can still be bounded explicitly with --limit.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://data.gov.ua/api/3/action/package_search"
PAGE_SIZE = 100


def fetch(q: str, rows: int = PAGE_SIZE, start: int = 0) -> dict:
    params = urllib.parse.urlencode({"q": q, "rows": rows, "start": start})
    with urllib.request.urlopen(f"{API}?{params}", timeout=60) as r:
        return json.load(r)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def discover(queries: list[str], limit: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for q in queries:
        start = 0
        while True:
            page = fetch(q, rows=PAGE_SIZE, start=start)
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
                        resources.append({
                            "name": clean(res.get("name")),
                            "format": clean(res.get("format")).upper(),
                            "url": url,
                        })
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="artifacts/discovery/data_gov_ua_catalog.json")
    ap.add_argument("--limit", type=int, default=0, help="0 = unlimited")
    args = ap.parse_args()
    queries = ["Україна", "Ukraine", "відкриті дані", "державний реєстр"]
    datasets = discover(queries, args.limit)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"source": "data.gov.ua", "datasets": datasets}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Discovered {len(datasets)} datasets")


if __name__ == "__main__": main()
