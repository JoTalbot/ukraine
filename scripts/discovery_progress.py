"""Guard index-based discovery progress against stale or changed catalogs."""
from __future__ import annotations

import hashlib
import json


def catalog_fingerprint(datasets: list[dict]) -> str:
    identities = [str(item.get("id") or item.get("name") or "") for item in datasets if isinstance(item, dict)]
    payload = json.dumps(identities, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def reconcile_progress(state: dict, batch_count: int, fingerprint: str) -> tuple[dict, bool]:
    result = dict(state)
    keys = ("successful_batches", "failed_batches", "blocked_batches")
    indexes = []
    for key in keys:
        values = result.get(key, [])
        if not isinstance(values, list):
            values = []
        parsed = []
        for value in values:
            try:
                parsed.append(int(value))
            except (TypeError, ValueError):
                parsed.append(-1)
        result[key] = sorted(set(parsed))
        indexes.extend(parsed)
    changed = result.get("batch_count") != batch_count or result.get("catalog_fingerprint") != fingerprint
    invalid = any(i < 0 or i >= batch_count for i in indexes)
    reset = changed or invalid
    if reset:
        result.update({"successful_batches": [], "failed_batches": [], "blocked_batches": [],
                       "completed_batches": 0, "next_batch": 0, "blocked_batch_count": 0,
                       "unreachable_hosts": [], "bootstrap_complete": False})
    result["batch_count"] = batch_count
    result["catalog_fingerprint"] = fingerprint
    return result, reset
