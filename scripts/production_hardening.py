"""Deterministic contracts for DRIFT, QUAR, REG, COMPAT, PROM and ROLL."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

V = 1
SHA256_HEX = 64


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and len(value) == SHA256_HEX and all(c in "0123456789abcdef" for c in value.lower())


def _valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def drift(baseline, current, output, max_row_change=0.20):
    base, actual = load(baseline), load(current)
    issues = []
    if base.get("schema_version") != V or actual.get("schema_version") != V:
        issues.append("unsupported schema")
    if base.get("schema_hash") != actual.get("schema_hash"):
        issues.append("schema_hash changed")
    base_rows, current_rows = base.get("row_count"), actual.get("row_count")
    if not isinstance(base_rows, int) or not isinstance(current_rows, int) or base_rows < 0 or current_rows < 0:
        issues.append("invalid row_count")
    elif base_rows and abs(current_rows - base_rows) / base_rows > max_row_change:
        issues.append("row_count threshold exceeded")
    if base.get("field_distributions", {}) != actual.get("field_distributions", {}):
        issues.append("field_distributions changed")
    if base.get("source_available") is not True or actual.get("source_available") is not True:
        issues.append("source unavailable")
    dump(output, {"schema_version": V, "state": "red" if issues else "green", "issues": issues, "max_row_change": max_row_change})
    return 1 if issues else 0


def quarantine(artifact, quarantine_dir, reason, source_commit, workflow_run_id, output):
    artifact = Path(artifact)
    if not artifact.is_file() or artifact.is_symlink():
        raise SystemExit(f"artifact must be a regular file: {artifact}")
    digest = sha(artifact)
    target = Path(quarantine_dir) / f"{artifact.name}.{digest}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or sha(target) != digest:
            raise SystemExit("immutable quarantine target checksum mismatch")
    else:
        shutil.copy2(artifact, target)
        if target.is_symlink() or not target.is_file() or sha(target) != digest:
            raise SystemExit("quarantine copy checksum mismatch")
    dump(output, {"schema_version": V, "state": "quarantined", "artifact": str(target), "sha256": digest, "reason": reason, "source_commit": source_commit, "workflow_run_id": workflow_run_id})
    return 0


def registry(model, model_id, dataset_revision, schema_hash, output, evaluation=None):
    model = Path(model)
    if not model.is_file():
        raise SystemExit(f"model not found: {model}")
    record = {"schema_version": V, "model_id": model_id, "artifact": str(model), "artifact_sha256": sha(model), "dataset_revision": dataset_revision, "schema_hash": schema_hash, "evaluation": load(evaluation) if evaluation else {}, "publication_state": "dev"}
    registry_path = Path(output)
    database = load(registry_path) if registry_path.is_file() else {"schema_version": V, "models": []}
    if database.get("schema_version") != V:
        raise SystemExit("unsupported registry schema")
    for old in database.get("models", []):
        if old.get("model_id") == model_id:
            if old != record:
                raise SystemExit("immutable model_id conflict")
            return 0
    database.setdefault("models", []).append(record)
    dump(registry_path, database)
    return 0


def compat(model_meta, dataset_meta, output):
    model, dataset = load(model_meta), load(dataset_meta)
    issues = []
    if model.get("dataset_revision") != dataset.get("revision"):
        issues.append("dataset revision mismatch")
    if model.get("schema_hash") != dataset.get("schema_hash"):
        issues.append("schema hash mismatch")
    dump(output, {"schema_version": V, "state": "red" if issues else "green", "issues": issues})
    return 1 if issues else 0


def promote(current_state, target_state, gates, output, *, model_id=None, artifact_sha256=None, evaluation_evidence_sha256=None, approval_identity=None, release_sequence=None, promoted_at=None):
    allowed = {"dev": {"validated"}, "validated": {"candidate"}, "candidate": {"production"}, "production": set(), "rolled_back": {"validated"}}
    gate_data = load(gates)
    issues = []
    if target_state not in allowed.get(current_state, set()):
        issues.append("invalid promotion transition")
    if target_state in {"validated", "candidate", "production"} and gate_data.get("compatibility") != "green":
        issues.append("compatibility gate not green")
    if target_state in {"candidate", "production"} and gate_data.get("evaluation") != "green":
        issues.append("evaluation gate not green")
    if target_state == "production" and gate_data.get("readiness") != "green":
        issues.append("readiness gate not green")
    event = None
    if target_state == "production":
        if not model_id:
            issues.append("production promotion requires model_id")
        if not _valid_sha(artifact_sha256):
            issues.append("production promotion requires artifact_sha256")
        if not _valid_sha(evaluation_evidence_sha256):
            issues.append("production promotion requires evaluation_evidence_sha256")
        if not approval_identity:
            issues.append("production promotion requires approval_identity")
        if not isinstance(release_sequence, int) or isinstance(release_sequence, bool) or release_sequence <= 0:
            issues.append("production promotion requires positive release_sequence")
        if not _valid_timestamp(promoted_at):
            issues.append("production promotion requires promoted_at")
        if not issues:
            event = {"schema_version": V, "event": "promote", "from": current_state, "to": target_state, "model_id": model_id, "artifact_sha256": artifact_sha256, "evaluation_evidence_sha256": evaluation_evidence_sha256, "approval_identity": approval_identity, "release_sequence": release_sequence, "promoted_at": promoted_at}
    result = {"schema_version": V, "from": current_state, "to": target_state, "state": "red" if issues else "green", "issues": issues}
    if event:
        result["promotion_event"] = event
    dump(output, result)
    return 1 if issues else 0


def rollback(registry, current_model_id, output):
    database = load(registry)
    good = [model for model in database.get("models", []) if model.get("publication_state") == "production" and model.get("model_id") != current_model_id]
    valid = [m for m in good if isinstance(m.get("release_sequence"), int) and m.get("release_sequence") > 0 and _valid_timestamp(m.get("promoted_at"))]
    target = max(valid, key=lambda m: (m["release_sequence"], m["promoted_at"])) if valid else None
    issues = [] if target else ["no immutable last-known-good production target"]
    result = {"schema_version": V, "state": "green" if target else "red", "current_model_id": current_model_id, "rollback_target": target, "issues": issues, "action": "restore rollback_target atomically" if target else "rollback refused"}
    dump(output, result)
    return 0 if target else 1


def evidence(output, source_commit, workflow_name, workflow_run_id):
    """Execute every hardening contract and negative safety checks against fixtures."""
    output = Path(output)
    with tempfile.TemporaryDirectory(prefix="ukraine-hardening-") as workdir:
        root = Path(workdir)
        base = {"schema_version": V, "schema_hash": "fixture-schema", "row_count": 10, "field_distributions": {"state": {"ok": 10}}, "source_available": True}
        dump(root / "baseline.json", base); dump(root / "current.json", base)
        drift_result = root / "drift.json"; drift(root / "baseline.json", root / "current.json", drift_result)
        artifact = root / "artifact.bin"; artifact.write_bytes(b"quarantine-fixture")
        quarantine_result = root / "quarantine.json"; quarantine(artifact, root / "quarantine", "self-test", source_commit, workflow_run_id, quarantine_result)
        tamper = root / "quarantine" / f"artifact.bin.{sha(artifact)}"; tamper.write_bytes(b"tampered")
        quarantine_tamper_rejected = False
        try:
            quarantine(artifact, root / "quarantine", "tamper-test", source_commit, workflow_run_id, root / "quarantine-tamper.json")
        except SystemExit:
            quarantine_tamper_rejected = True
        if not quarantine_tamper_rejected:
            raise SystemExit("negative quarantine tamper test failed")
        model = root / "model.bin"; model.write_bytes(b"model-fixture")
        registry_result = root / "registry.json"; registry(model, "fixture-model", "dataset-1", "fixture-schema", registry_result)
        dump(root / "model-meta.json", {"dataset_revision": "dataset-1", "schema_hash": "fixture-schema"}); dump(root / "dataset-meta.json", {"revision": "dataset-1", "schema_hash": "fixture-schema"})
        compat_result = root / "compat.json"; compat(root / "model-meta.json", root / "dataset-meta.json", compat_result)
        gates = root / "gates.json"; dump(gates, {"compatibility": "green", "evaluation": "green", "readiness": "green"})
        promote_result = root / "promote.json"
        missing_promotion_rejected = promote("candidate", "production", gates, promote_result) == 1
        if not missing_promotion_rejected:
            raise SystemExit("negative promotion metadata test failed")
        evaluation_sha = sha(root / "model.bin")
        promoted_at = datetime.now(timezone.utc).isoformat()
        promotion_rc = promote("candidate", "production", gates, promote_result, model_id="fixture-model", artifact_sha256=sha(model), evaluation_evidence_sha256=evaluation_sha, approval_identity="self-test", release_sequence=1, promoted_at=promoted_at)
        if promotion_rc != 0:
            raise SystemExit("positive promotion self-test failed")
        database = load(registry_result); database["models"][0].update({"publication_state": "production", "release_sequence": 1, "promoted_at": promoted_at}); database["models"].append({**database["models"][0], "model_id": "fixture-current", "release_sequence": 2, "promoted_at": datetime.now(timezone.utc).isoformat()}); dump(registry_result, database)
        rollback_result = root / "rollback.json"; rollback(registry_result, "fixture-current", rollback_result)
        results = {"DRIFT-01": load(drift_result), "QUAR-01": load(quarantine_result), "REG-01": {"state": "green" if load(registry_result).get("models") else "red"}, "COMPAT-01": load(compat_result), "PROM-01": load(promote_result), "ROLL-01": load(rollback_result)}
        states = [item.get("state") for item in results.values()]
        state = "green" if all(value in {"green", "quarantined"} for value in states) else "red"
        dump(output, {"schema_version": V, "state": state, "source_commit": source_commit, "workflow_name": workflow_name, "workflow_run_id": workflow_run_id, "negative_tests": {"quarantine_tamper_rejected": quarantine_tamper_rejected, "promotion_missing_metadata_rejected": missing_promotion_rejected}, "contracts": results})
    return 0 if state == "green" else 1


def main():
    parser = argparse.ArgumentParser(); subparsers = parser.add_subparsers(dest="cmd", required=True)
    command = subparsers.add_parser("drift"); command.add_argument("baseline"); command.add_argument("current"); command.add_argument("output"); command.add_argument("--max-row-change", type=float, default=0.20)
    command = subparsers.add_parser("quarantine"); command.add_argument("artifact"); command.add_argument("quarantine_dir"); command.add_argument("reason"); command.add_argument("source_commit"); command.add_argument("workflow_run_id"); command.add_argument("output")
    command = subparsers.add_parser("registry"); command.add_argument("model"); command.add_argument("model_id"); command.add_argument("dataset_revision"); command.add_argument("schema_hash"); command.add_argument("output"); command.add_argument("--evaluation")
    command = subparsers.add_parser("compat"); command.add_argument("model_meta"); command.add_argument("dataset_meta"); command.add_argument("output")
    command = subparsers.add_parser("promote"); command.add_argument("current_state"); command.add_argument("target_state"); command.add_argument("gates"); command.add_argument("output"); command.add_argument("--model-id"); command.add_argument("--artifact-sha256"); command.add_argument("--evaluation-evidence-sha256"); command.add_argument("--approval-identity"); command.add_argument("--release-sequence", type=int); command.add_argument("--promoted-at")
    command = subparsers.add_parser("rollback"); command.add_argument("registry"); command.add_argument("current_model_id"); command.add_argument("output")
    command = subparsers.add_parser("evidence"); command.add_argument("output"); command.add_argument("source_commit"); command.add_argument("workflow_name"); command.add_argument("workflow_run_id")
    args = vars(parser.parse_args()); command_name = args.pop("cmd"); raise SystemExit(globals()[command_name](**args))


if __name__ == "__main__":
    main()
