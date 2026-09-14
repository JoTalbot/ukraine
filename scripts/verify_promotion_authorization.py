"""Fail-closed verification of authoritative production promotion authorization."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

V = 1
AUTH = "artifacts/status/production-promotion-authorization.json"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""): h.update(chunk)
    return h.hexdigest()

def valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())

def verify(root: Path) -> tuple[bool, list[str]]:
    issues: list[str] = []
    root = Path(root)
    auth_path = root / AUTH
    manifest_path = root / "artifacts/status/release-manifest.json"
    if not auth_path.is_file(): return False, [f"missing authorization: {AUTH}"]
    if not manifest_path.is_file(): issues.append("missing release manifest")
    try: auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError): return False, ["authorization is invalid JSON"]
    try: manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError): manifest = {}
    if auth.get("schema_version") != V: issues.append("unsupported authorization schema")
    if auth.get("target") != "production": issues.append("authorization target is not production")
    if not auth.get("source_commit") or auth.get("source_commit") != manifest.get("git_commit"): issues.append("authorization commit does not match release manifest")
    if not auth.get("model_id"): issues.append("missing model_id")
    for key in ("artifact_sha256", "evaluation_evidence_sha256"):
        if not valid_sha(auth.get(key)): issues.append(f"invalid {key}")
    for key in ("artifact_path", "evaluation_evidence_path"):
        if not isinstance(auth.get(key), str) or not auth.get(key): issues.append(f"missing {key}")
    artifact = root / auth.get("artifact_path", "__missing__")
    evaluation = root / auth.get("evaluation_evidence_path", "__missing__")
    if artifact.is_file() and valid_sha(auth.get("artifact_sha256")) and sha256(artifact) != auth["artifact_sha256"]: issues.append("production artifact checksum mismatch")
    elif not artifact.is_file(): issues.append("production artifact is missing")
    if evaluation.is_file() and valid_sha(auth.get("evaluation_evidence_sha256")) and sha256(evaluation) != auth["evaluation_evidence_sha256"]: issues.append("evaluation evidence checksum mismatch")
    elif not evaluation.is_file(): issues.append("evaluation evidence is missing")
    if not auth.get("approval_identity"): issues.append("missing approval_identity")
    if not isinstance(auth.get("release_sequence"), int) or isinstance(auth.get("release_sequence"), bool) or auth.get("release_sequence") <= 0: issues.append("invalid release_sequence")
    if not isinstance(auth.get("approved_at"), str) or not auth.get("approved_at"): issues.append("missing approved_at")
    return not issues, issues

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--root", default="."); p.add_argument("--output", default="artifacts/status/promotion-authorization-verification.json"); a = p.parse_args()
    ok, issues = verify(Path(a.root))
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps({"schema_version": V, "state": "green" if ok else "red", "authorization": AUTH, "issues": issues}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"state": "green" if ok else "red", "issues": issues}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)

if __name__ == "__main__": main()
