from __future__

import json

from scripts import security_scan


def test_secret_scanner_detects_high_confidence_credentials(tmp_path) -> None:
    fake_token = "g" + "hp_" + "a" * 36
    fake_private_key = "-----BEGIN " + "PRIVATE KEY-----"
    files = [
        (tmp_path / "secret.txt", f"token = '{fake_token}'\n"),
        (tmp_path / "key.txt", fake_private_key + "\n"),
    ]
    findings = security_scan.scan_secrets(files)
    assert {item["kind"] for item in findings} == {"github_token", "private_key"}


def test_secret_scanner_ignores_placeholders_and_public_hashes(tmp_path) -> None:
    files = [
        (tmp_path / "example.py", "API_KEY = 'YOUR_API_KEY_HERE'\npassword = '${PASSWORD}'\n"),
        (tmp_path / "manifest.json", '"sha256": "' + "a" * 64 + '"\n'),
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
    for name in security_scan.PRIVACY_REQUIRED_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("no_deanonymization public_open_data_only", encoding="utf-8")
    manifest = tmp_path / ".training-manifests" / "test" / "training_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"privacy_scope": "public_open_data_only", "deanonymization": False}),
        encoding="utf-8",
    )
    monkeypatch.setattr(security_scan, "ROOT", tmp_path)
    monkeypatch.setattr(
        security_scan,
        "tracked_files",
        lambda: [tmp_path / name for name in security_scan.PRIVACY_REQUIRED_FILES] + [manifest],
    )
    first = security_scan.build_evidence("abc", "workflow", "1")
    second = security_scan.build_evidence("abc", "workflow", "1")
    assert first == second
