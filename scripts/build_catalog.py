#!/usr/bin/env python3
"""Build a reproducible catalog from the configured public-data sources."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config' / 'priority_open_data_sources.yml'
OUT = ROOT / 'artifacts' / 'catalog.json'

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    # Keep the catalog dependency-free: preserve configured source definitions
    # and enrich it with local artifact metadata when files exist.
    text = CONFIG.read_text(encoding='utf-8') if CONFIG.exists() else ''
    files = []
    for p in (ROOT / 'artifacts').rglob('*') if (ROOT / 'artifacts').exists() else []:
        if p.is_file() and p != OUT:
            files.append({'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': sha256_file(p)})
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'config_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'git_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'configured_sources_file': str(CONFIG.relative_to(ROOT)),
        'artifact_count': len(files),
        'artifacts': files,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
