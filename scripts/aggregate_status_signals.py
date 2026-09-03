"""Aggregate workflow-produced status signals into the canonical control-plane index."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = 1
SIGNALS = ("ci", "ingestion", "quality", "graph", "training", "publication", "security")
PRODUCER_SIGNALS = set(SIGNALS) - {"ci", "security"}
VALID_STATES = {"green", "yellow", "red", "unknown"}
FRESHNESS_HOURS = {"ingestion": 48, "quality": 48, "graph": 168, "training": 168, "publication": 48}
PRECEDENCE = {"unknown": 0, "green": 1, "yellow": 2, "red": 3}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _freshness(signal: dict, expected_name: str, now: datetime) -> dict:
    if expected_name not in FRESHNESS_HOURS:
        return signal
    raw = signal.get("generated_at_utc")
    if not isinstance(raw, str):
        return {**signal, "state": "unknown", "detail": "signal has no generation timestamp"}
    try:
        generated = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return {**signal, "state": "unknown", "detail": "signal has invalid generation timestamp"}
    age = now - generated
    if age < timedelta(0):
        return {**signal, "state": "unknown", "detail": "signal generation timestamp is in the future"}
    if age > timedelta(hours=FRESHNESS_HOURS[expected_name]):
        return {**signal, "state": "unknown", "detail": f"signal is stale (>{FRESHNESS_HOURS[expected_name]}h)"}
    result = dict(signal)
    result["age_hours"] = round(age.total_seconds() / 3600, 2)
    result["freshness_hours"] = FRESHNESS_HOURS[expected_name]
    return result


def normalize_signal(path: Path, expected_name: str, release_commit: str, now: datetime | None = None) -> dict:
    missing = {"state": "unknown", "detail": "no signal artifact recorded"}
    if not path.is_file():
        return missing
    try:
        payload = load_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"state": "red", "detail": "signal artifact is invalid JSON"}
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("signal") != expected_name:
        return {"state": "red", "detail": "signal artifact schema is invalid"}
    source_commit = payload.get("source_commit", payload.get("git_commit"))
    if source_commit != release_commit:
        return {"state": "unknown", "detail": "signal belongs to a different release commit"}
    if payload.get("state") not in VALID_STATES:
        return {"state": "red", "detail": "signal artifact has an invalid state"}
    result = {"state": payload["state"], "detail": str(payload.get("detail", ""))[:500]}
    for field in ("workflow_name", "workflow_run_id", "artifact"):
        if payload.get(field) not in (None, ""):
            result[field] = str(payload[field])[:200]
    result["generated_at_utc"] = payload.get("generated_at_utc", "")
    return _freshness(result, expected_name, now or datetime.now(timezone.utc))


def build_status_index(manifest_path: Path, signals_dir: Path, sbom_path: Path | None = None) -> dict:
    manifest = load_json(manifest_path)
    release_commit = manifest.get("git_commit")
    if not release_commit:
        raise ValueError("release manifest has no git_commit")

    signals = {name: {"state": "unknown", "detail": "no signal artifact recorded"} for name in SIGNALS}
    signals["ci"] = {"state": "green", "detail": "repository validation completed"}
    signals["security"] = {"state": "green", "detail": "repository security contract completed"}
    for name in PRODUCER_SIGNALS:
        signals[name] = normalize_signal(signals_dir / f"{name}.json", name, release_commit)

    overall_state = max((item["state"] for item in signals.values()), key=lambda state: PRECEDENCE[state])
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": "ukraine",
        "overall_state": overall_state,
        "policy": {
            "precedence": ["unknown", "green", "yellow", "red"],
            "freshness_hours": FRESHNESS_HOURS,
            "missing_producer_state": "unknown",
            "stale_producer_state": "unknown",
        },
        "release": {
            "class": manifest.get("release_class"),
            "git_commit": release_commit,
            "git_branch": manifest.get("git_branch"),
            "manifest": str(manifest_path),
            "file_count": len(manifest.get("files", [])),
        },
        "runtime": {"python": platform.python_version()},
        "signals": signals,
    }
    if sbom_path is not None:
        if not sbom_path.is_file():
            raise ValueError(f"SBOM path does not exist: {sbom_path}")
        result["supply_chain"] = {
            "sbom": str(sbom_path),
            "format": "CycloneDX",
            "sha256": sha256(sbom_path),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="artifacts/status/release-manifest.json")
    parser.add_argument("--signals-dir", default="artifacts/status/signals")
    parser.add_argument("--sbom", default=None)
    parser.add_argument("--output", default="artifacts/status/status-index.json")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_status_index(Path(args.manifest), Path(args.signals_dir), Path(args.sbom) if args.sbom else None)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"aggregated status index written: {output}")


if __name__ == "__main__":
    main()
