from __future__ import annotations

import json
from pathlib import Path

from scripts import security_scan


def test_secret_scanner_detects_high_confidence_credentials() -> None:
    files = [
        (Path("secret.txt"), "token = 'ghp_abcdefghijklmnopqrstuvwxyz1234567890'\n"),
        (Path("key.txt"), "-----BEGIN PRIVATE KEY-----\n"),
    ]
    findings = security_scan.scan_secrets(files)
    assert {item["kind"] for item in findings} == {"github_token", "private_key"}


def test_secret_scanner_ignores_placeholders_and_public_hashes() -> None:
    files = [
        (Path("example.py"), "API_KEY = 'YOUR_API_KEY_HERE'\npassword = '${PASSWORD}'\n"),
        (Path("manifest.json"), '"sha256": "' + "a" * 64 + '"\n'),
    ]
    assert security_scan.scan_secrets(files) == []


def test_privacy_contract_covers_required_files_and_training_manifests() -> None:
    files = {
        name: "no_deanonymization public_open_data_only"
        for name in security_scan.PRIVACY_REQUIRED_FILES
    }
    files[".training-manifests/test/training_manifest.json"] = json.dumps(
        {"privacy_scope": "public_open_data_only", "deanonymization": False}
    )
    assert security_scan.check_privacy(files) == []


def test_privacy_contract_rejects_deanonymization() -> None:
    files = {
        name: "no_deanonymization public_open_data_only"
        for name in security_scan.PRIVACY_REQUIRED_FILES
    }
    files[".training-manifests/test/training_manifest.json"] = json.dumps(
        {"privacy_scope": "public_open_data_only", "deanonymization": True}
    )
    findings = security_scan.check_privacy(files)
    assert {item["kind"] for item in findings} == {"deanonymization_enabled"}


def test_evidence_is_deterministic_for_same_tree(monkeypatch, tmp_path) -> None:
    files = [(Path("README.md"), "no_deanonymization public_open_data_only")]
    monkeypatch.setattr(security_scan, "tracked_files", lambda: [tmp_path / "README.md"])
    (tmp_path / "README.md").write_text(files[0][1], encoding="utf-8")
    first = security_scan.build_evidence("abc", "workflow", "1")
    second = security_scan.build_evidence("abc", "workflow", "1")
    assert first == second
