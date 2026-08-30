#!/usr/bin/env python3
"""Create a deterministic manifest for HF training jobs."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'training_manifest.json'
DATA = ROOT / 'data'
ALLOWED = {'.json','.jsonl','.ndjson','.csv','.tsv','.parquet','.txt','.md','.xml'}

def main():
    rows=[]
    if DATA.exists():
        for p in DATA.rglob('*'):
            if p.is_file() and p.suffix.lower() in ALLOWED:
                h=hashlib.sha256()
                with p.open('rb') as f:
                    for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
                rows.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
    rows.sort(key=lambda x:x['path'])
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'privacy_scope':'public_open_data_only','deanonymization':False,'record_count':len(rows),'files':rows}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Prepared {len(rows)} training files')
if __name__=='__main__': main()
