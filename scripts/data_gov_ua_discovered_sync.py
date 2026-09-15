#!/usr/bin/env python3
"""Mirror discovered data.gov.ua datasets to Hugging Face with incremental refresh.

Fail-closed accounting with a host pre-flight:

* a resource that cannot be fetched because **its source host is unreachable**
  is reported as ``blocked`` (external blocker), not as ``failed`` (pipeline
  error) — the two have different owners and different fixes;
* each distinct source host is probed **once per run** (short timeout) before
  any download is attempted, so a dead host costs seconds instead of
  ``FETCH_ATTEMPTS x REQUEST_TIMEOUT`` per resource.

Why this exists: since 2026-09-14 ``opendata.gov.ua`` accepts TCP connections
but never completes the TLS handshake, and it hosts ~90% of discovered
resources. Without the pre-flight every batch spent the full 150-minute job
timeout on timeouts and was recorded as a plain failure, which hid the real
cause (an unreachable upstream) behind a wall of red batches.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import socket
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from huggingface_hub import HfApi
from huggingface_hub.utils import EntryNotFoundError

CHUNK = 8 * 1024 * 1024
FETCH_ATTEMPTS = int(os.environ.get("DATA_GOV_FETCH_ATTEMPTS", "3"))
REQUEST_TIMEOUT = (30, 60)
MAX_RETRY_WAIT = int(os.environ.get("DATA_GOV_MAX_RETRY_WAIT", "60"))
HOST_PROBE_TIMEOUT = float(os.environ.get("DATA_GOV_HOST_PROBE_TIMEOUT", "15"))
HEADERS = {"User-Agent": "JoTalbot/ukraine-open-data-sync"}
STRUCTURED = {"CSV", "TSV", "JSON", "JSONL", "NDJSON", "XML", "XLS", "XLSX", "ODS", "PARQUET", "ZIP", "7Z", "GZ", "GZIP"}
RETRYABLE_STATUS_CODES = {408, 425, 429}
SOURCE_UNAVAILABLE = "source_unavailable"
SOURCE_THROTTLED = "source_throttled"
RESOURCE_ERROR = "resource_error"
# Внешние причины (не наша ошибка): считаются блокерами источника, а не отказом ресурса
EXTERNAL_KINDS = {SOURCE_UNAVAILABLE, SOURCE_THROTTLED}


def _retry_wait(resp, attempt):
    """Return a bounded retry delay, honoring a server-provided Retry-After hint."""
    retry_after = resp.headers.get("Retry-After") if resp is not None else None
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), float(MAX_RETRY_WAIT))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is not None:
                    delay = retry_at.timestamp() - time.time()
                    return min(max(delay, 0.0), float(MAX_RETRY_WAIT))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(float(2**attempt), float(MAX_RETRY_WAIT))


def download_with_retries(url, dest):
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        resp = None
        try:
            with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT, headers=HEADERS) as response:
                resp = response
                if response.status_code in RETRYABLE_STATUS_CODES or 500 <= response.status_code <= 599:
                    raise requests.HTTPError(f"server replied {response.status_code}", response=response)
                response.raise_for_status()
                total = 0
                with dest.open("wb") as f:
                    for chunk in response.iter_content(CHUNK):
                        if chunk:
                            total += len(chunk)
                            f.write(chunk)
            return total
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.HTTPError,
        ) as exc:
            dest.unlink(missing_ok=True)
            if attempt == FETCH_ATTEMPTS:
                raise
            wait = _retry_wait(resp, attempt)
            print(f"download attempt {attempt}/{FETCH_ATTEMPTS} failed for {url}: {exc!r}; retrying in {wait:g}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def safe(s):
    return (re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ._-]+", "_", s or "resource")[:180] or "resource")


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resource_signature(r):
    return {"url": r.get("url"), "hash": r.get("hash"), "last_modified": r.get("last_modified"), "size": r.get("size")}


def same_resource(a, r):
    sig = resource_signature(r)
    if a.get("url") != sig["url"]:
        return False
    if sig["hash"]:
        return a.get("source_hash") == sig["hash"]
    if sig["last_modified"] is not None or sig["size"] is not None:
        return a.get("source_last_modified") == sig["last_modified"] and a.get("source_size") == sig["size"]
    return False


# ------------------------------------------------------------------ хосты

def host_of(url) -> str:
    """Домен источника без схемы и порта ('' для относительных ссылок)."""
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def probe_host(host, timeout: float | None = None) -> dict:
    """Живой ли хост-источник: TCP-connect + HTTPS HEAD с коротким таймаутом.

    Любой HTTP-ответ (включая 403/404) означает, что хост жив. Ошибка
    соединения или отсутствие ответа — недоступен. Именно так выглядит
    opendata.gov.ua с 14.09.2026: TCP открывается, а TLS-хендшейк молчит.
    """
    timeout = HOST_PROBE_TIMEOUT if timeout is None else timeout
    result = {"host": host, "reachable": False, "latency_ms": None, "detail": ""}
    if not host:
        result["detail"] = "empty host"
        return result
    started = time.monotonic()
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            pass
    except OSError as exc:
        result["detail"] = f"tcp: {type(exc).__name__}: {exc}"
        return result
    try:
        response = requests.head(f"https://{host}/", timeout=(timeout, timeout), headers=HEADERS, allow_redirects=True)
        result["reachable"] = True
        result["detail"] = f"http {response.status_code}"
    except requests.exceptions.RequestException as exc:
        result["detail"] = f"https: {type(exc).__name__}: {exc}"
    except Exception as exc:
        result["detail"] = f"https: {type(exc).__name__}: {exc}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


def probe_hosts(hosts, timeout: float | None = None) -> dict:
    """Предпроверка всех хостов батча (каждый — один раз за запуск)."""
    health = {}
    for host in sorted({h for h in hosts if h}):
        health[host] = probe_host(host, timeout)
        status = "доступен" if health[host]["reachable"] else "НЕДОСТУПЕН"
        print(f"host pre-flight {host}: {status} ({health[host]['detail']}, {health[host]['latency_ms']} ms)")
    return health


def classify_exception(exc) -> str:
    """Отличить проблему источника (недоступен/троттлит) от ошибки самого ресурса."""
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return SOURCE_UNAVAILABLE
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 429:
            return SOURCE_THROTTLED
        if 500 <= status <= 599:
            return SOURCE_THROTTLED
    return RESOURCE_ERROR


# ------------------------------------------------------------------ батч

def sync_dataset(ds, ctx) -> dict:
    """Обработать один датасет: скачать ресурсы, загрузить в HF, вернуть запись."""
    root: Path = ctx["root"]
    hf = ctx["hf"]
    repo = ctx["repo"]
    args = ctx["args"]
    previous = ctx["previous"]
    health = ctx["health"]
    ds_id = safe(ds.get("id") or ds.get("name"))
    resources = [r for r in ds.get("resources", []) if r.get("url") and r.get("format", "").upper() in STRUCTURED]
    if args.max_dataset_files > 0:
        resources = resources[: args.max_dataset_files]
    old = previous.get(ds.get("url"), {})
    old_files = {x.get("source_url"): x for x in old.get("files", [])}
    entry = {
        "id": ds_id,
        "name": ds.get("name"),
        "source_url": ds.get("url"),
        "modified": ds.get("modified"),
        "files": [],
        "failed": [],
        "blocked": [],
    }
    for i, r in enumerate(resources):
        url = r["url"]
        dest = None
        prior = old_files.get(url)
        host = host_of(url)
        if host and host in health and not health[host]["reachable"]:
            entry["blocked"].append({
                "url": url,
                "host": host,
                "kind": SOURCE_UNAVAILABLE,
                "reason": f"source host unreachable: {health[host]['detail']}",
            })
            continue
        try:
            if args.incremental and prior and same_resource(prior, r):
                entry["files"].append(prior)
                print(f"Unchanged, skipped download: {url}")
                continue
            name = safe(r.get("name") or Path(url.split("?")[0]).name or f"resource-{i}")
            name += "." + r.get("format", "bin").lower() if "." not in name else ""
            dest = root / ds_id / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            total = download_with_retries(url, dest)
            if args.max_file_mb > 0 and total > args.max_file_mb * 1024 * 1024:
                raise RuntimeError(f"resource exceeds --max-file-mb: {total} bytes")
            sha = file_sha256(dest)
            target = f"discovered/{ds_id}/{name}"
            if hf is not None:
                hf.upload_file(path_or_fileobj=str(dest), path_in_repo=target, repo_id=repo, repo_type="dataset")
            entry["files"].append(
                {
                    "path": target,
                    "source_url": url,
                    "source_hash": r.get("hash"),
                    "source_last_modified": r.get("last_modified"),
                    "source_size": r.get("size"),
                    "sha256": sha,
                    "bytes": total,
                    "format": r.get("format"),
                }
            )
            print(f"Uploaded {target} ({total} bytes)" if hf is not None else f"Downloaded (dry-run) {target} ({total} bytes)")
        except Exception as exc:
            kind = classify_exception(exc)
            if kind in EXTERNAL_KINDS:
                if kind == SOURCE_UNAVAILABLE and host:
                    # хост упал уже после предпроверки — фиксируем как блокер источника
                    health.setdefault(host, {"host": host, "reachable": False, "latency_ms": None, "detail": "failed during download"})
                    health[host]["reachable"] = False
                entry["blocked"].append({"url": url, "host": host, "kind": kind, "reason": str(exc)})
                print(f"Source blocked during download ({kind}): {url}: {exc}")
            else:
                entry["failed"].append({"url": url, "host": host, "kind": RESOURCE_ERROR, "reason": str(exc)})
                print(f"Resource failed: {url}: {exc}")
        finally:
            if dest is not None:
                with contextlib.suppress(Exception):
                    dest.unlink(missing_ok=True)
    return entry


def load_manifest(hf, repo, offset):
    try:
        path = hf.hf_hub_download(
            repo_id=repo,
            filename=f"batch-manifests/discovered-manifest-{offset}.json",
            repo_type="dataset",
            local_dir=".manifest-cache",
        )
    except EntryNotFoundError:
        print(f"No prior manifest for batch offset {offset}: first incremental run for this batch")
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Invalid prior manifest for batch offset {offset}: expected a JSON list")
    return {x["source_url"]: x for x in data}


def write_source_health(health, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "hosts": [health[h] for h in sorted(health)],
        "unreachable_hosts": sorted(h for h in health if not health[h]["reachable"]),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="artifacts/discovery/data_gov_ua_catalog.json")
    ap.add_argument("--max-dataset-files", type=int, default=0)
    ap.add_argument("--max-file-mb", type=int, default=0)
    ap.add_argument("--dataset-offset", type=int, default=0)
    ap.add_argument("--dataset-limit", type=int, default=250)
    ap.add_argument("--output", default="artifacts/discovered-open-data")
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--allow-failures", action="store_true", help="record resource failures but exit successfully")
    ap.add_argument("--probe-timeout", type=float, default=HOST_PROBE_TIMEOUT,
                    help="таймаут предпроверки хоста-источника, сек")
    ap.add_argument("--no-host-probe", action="store_true",
                    help="отключить предпроверку хостов (отладочный режим: всё качается как раньше)")
    ap.add_argument("--dry-run", action="store_true",
                    help="скачать и проверить, но ничего не загружать в Hugging Face (не нужен HF_TOKEN)")
    ap.add_argument("--health-output", default="artifacts/discovery/source-health.json",
                    help="куда записать отчёт о доступности хостов-источников")
    args = ap.parse_args()
    if args.dataset_offset < 0 or args.dataset_limit < 0:
        raise SystemExit("dataset offset/limit must be >= 0")
    token = os.environ.get("HF_TOKEN")
    repo = os.environ.get("HF_DATASET_REPO", "JoTalbot/ua-open-data")
    if not token and not args.dry_run:
        raise SystemExit("HF_TOKEN secret is missing")
    all_datasets = json.loads(Path(args.catalog).read_text(encoding="utf-8")).get("datasets", [])
    datasets = all_datasets[args.dataset_offset : args.dataset_offset + args.dataset_limit] if args.dataset_limit else all_datasets[args.dataset_offset :]
    hf = None if args.dry_run else HfApi(token=token)
    if hf is not None:
        hf.create_repo(repo_id=repo, repo_type="dataset", exist_ok=True, private=False)
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    previous = load_manifest(hf, repo, args.dataset_offset) if args.incremental and hf is not None else {}

    hosts = {host_of(r["url"]) for ds in datasets for r in ds.get("resources", []) if r.get("url")}
    health = {} if args.no_host_probe else probe_hosts(hosts, timeout=args.probe_timeout)

    ctx = {"root": root, "hf": hf, "repo": repo, "args": args, "previous": previous, "health": health}
    decisions = [sync_dataset(ds, ctx) for ds in datasets]

    failures = [{"dataset": x["id"], **f} for x in decisions for f in x.get("failed", [])]
    blocked = [{"dataset": x["id"], **b} for x in decisions for b in x.get("blocked", [])]
    unreachable = sorted(h for h in health if not health[h]["reachable"])
    if health:
        print(f"Source health written: {write_source_health(health, args.health_output)}")

    manifest = root / "discovered-manifest.json"
    manifest.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    if hf is not None:
        hf.upload_file(
            path_or_fileobj=str(manifest),
            path_in_repo=f"batch-manifests/discovered-manifest-{args.dataset_offset}.json",
            repo_id=repo,
            repo_type="dataset",
        )
    summary = {
        "datasets": len(decisions),
        "downloaded": sum(len(x.get("files", [])) for x in decisions),
        "resource_failures": len(failures),
        "blocked_resources": len(blocked),
        "unreachable_hosts": unreachable,
    }
    print("BATCH SUMMARY " + json.dumps(summary, ensure_ascii=False))
    if failures:
        print(f"Batch has {len(failures)} real resource failure(s); the pipeline must not advance")
    if blocked:
        print(
            f"Batch blocked by unreachable source host(s) {unreachable or 'unknown'}: "
            f"{len(blocked)} resource(s) not fetched. This is an external blocker, not a pipeline error."
        )
    if (failures or blocked) and not args.allow_failures:
        if failures:
            raise SystemExit(f"Batch incomplete: {len(failures)} resource(s) failed; progress must not advance")
        raise SystemExit(
            f"Batch blocked: {len(blocked)} resource(s) on unreachable host(s) {unreachable}; progress must not advance"
        )
    if failures or blocked:
        print("Batch recorded with failures/blockers; caller may schedule a retry pass")


if __name__ == "__main__":
    main()
