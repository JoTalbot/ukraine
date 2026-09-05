#!/usr/bin/env python3
"""Deterministic repository security/privacy boundary scan for SEC-01."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("basic_auth_url", re.compile(r"https?://[^\s/@:]+:[^\s/@]+@[^\s]+", re.IGNORECASE)),
    (
        "secret_assignment",
        re.compile(
            r"\b(?:api[_-]?key|access[_-]?token|secret|password|passwd)\b\s*[:=]\s*['\"](?!$|(?:YOUR_|REPLACE_|EXAMPLE|CHANGEME|REDACTED|<|\$\{|os\.environ|getenv))[^'\"]{12,}['\"]",
            re.IGNORECASE,
        ),
    ),
)

PRIVACY_REQUIRED_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "docs/ENTITY_LINKS.md",
    "scripts/build_lm_corpus.py",
    "schemas/entity_links.sql",
)

REQUIRED_PRIVACY_MARKERS = ("no_deanonymization", "public_open_data_only")


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=False,
    )
    return [ROOT / item for item in result.stdout.decode("utf-8").split("\0") if item]


def iter_text_files(paths: Iterable[Path]) -> Iterable[tuple[Path, str]]:
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        try:
            yield path, data.decode("utf-8")
        except UnicodeDecodeError:
            continue


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def scan_secrets(files: Iterable[tuple[Path, str]]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path, content in files:
        for line_no, line in enumerate(content.splitlines(), 1):
            for kind, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append({"path": display_path(path), "line": line_no, "kind": kind})
    return findings


def check_training_manifest(path: str, payload: object) -> list[dict[str, str]]:
    records = payload if isinstance(payload, list) else [payload]
    findings: list[dict[str, str]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            findings.append({"kind": "invalid_training_manifest_record", "path": path, "record": str(index)})
            continue
        if record.get("privacy_scope") != "public_open_data_only":
            findings.append({"kind": "invalid_training_privacy_scope", "path": path, "record": str(index)})
        if record.get("deanonymization") is not False:
            findings.append({"kind": "deanonymization_enabled", "path": path, "record": str(index)})
    return findings


def check_privacy(files: dict[str, str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name in PRIVACY_REQUIRED_FILES:
        content = files.get(name)
        if content is None:
            findings.append({"kind": "missing_privacy_policy_file", "path": name})
            continue
        for marker in REQUIRED_PRIVACY_MARKERS:
            if marker not in content:
                findings.append({"kind": "missing_privacy_marker", "path": name, "marker": marker})

    for path, content in sorted(files.items()):
        if not path.startswith(".training-manifests/") or not path.endswith(".json"):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            findings.append({"kind": "invalid_training_manifest", "path": path})
            continue
        findings.extend(check_training_manifest(path, payload))
    return findings


def build_evidence(source_commit: str, workflow_name: str, workflow_run_id: str) -> dict[str, object]:
    files = list(iter_text_files(tracked_files()))
    by_name = {display_path(path): content for path, content in files}
    secret_findings = scan_secrets(files)
    privacy_findings = check_privacy(by_name)
    findings = secret_findings + privacy_findings
    payload: dict[str, object] = {
        "schema_version": 1,
        "contract": "SEC-01",
        "source_commit": source_commit,
        "workflow_name": workflow_name,
        "workflow_run_id": workflow_run_id,
        "policy": {
            "public_open_data_only": True,
            "no_deanonymization": True,
        },
        "tracked_text_files_scanned": len(files),
        "findings": findings,
        "state": "green" if not findings else "red",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["evidence_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--workflow-name", default="local")
    parser.add_argument("--workflow-run-id", default="local")
    args = parser.parse_args()

    evidence = build_evidence(args.source_commit, args.workflow_name, args.workflow_run_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if evidence["state"] != "green":
        print(json.dumps({"contract": "SEC-01", "state": "red", "finding_count": len(evidence["findings"])}, sort_keys=True))
        return 1
    print(json.dumps({"contract": "SEC-01", "state": "green", "scanned": evidence["tracked_text_files_scanned"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
