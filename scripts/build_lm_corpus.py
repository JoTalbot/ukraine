#!/usr/bin/env python3
"""Build a Ukrainian legal-domain text corpus from mirrored open data.

Sources (any subset):
- EDRSR Parquet parts  -> "Суд ... Справа № ... Категорія ... Суддя ... Рішення ..."
- EDR UO.zip (XML)     -> company profiles with founders and charter excerpts
- VAT registry CSV     -> payer lines

Output: one UTF-8 sentence/line per record, deduplicated, shuffled.
Used to train the small Ukrainian legal LM (scripts/train_lm.py).

Privacy: only fields already published as open data; source anonymization
is preserved (no_deanonymization).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def iter_edr_uo(zip_path: str | Path):
    with zipfile.ZipFile(zip_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        with zf.open(member) as stream:
            parser = ET.iterparse(stream, events=("start", "end"))
            root = None
            for event, elem in parser:
                if event == "start" and root is None:
                    root = elem
                if event == "end" and elem.tag.strip().upper().endswith("SUBJECT"):
                    yield {
                        "name": _text(elem.find("NAME")),
                        "opf": _text(elem.find("OPF")),
                        "edrpou": _text(elem.find("EDRPOU")),
                        "stan": _text(elem.find("STAN")),
                        "founders": [_text(f) for f in elem.findall(".//FOUNDER") if _text(f)],
                        "statute": _text(elem.find("STATUTE"))[:220],
                    }
                    root.clear()


def iter_vat_csv(path: str | Path):
    import csv
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            yield {k: (v or "").strip() for k, v in row.items() if k}


def edrsr_line(row: dict) -> str:
    parts = []
    if row.get("court"):
        parts.append(f"Суд: {row['court']}.")
    if row.get("case_number"):
        parts.append(f"Справа № {row['case_number']}.")
    if row.get("category"):
        parts.append(f"Категорія: {row['category']}.")
    if row.get("judge"):
        parts.append(f"Суддя: {row['judge']}.")
    if row.get("decision_date"):
        parts.append(f"Рішення від {str(row['decision_date'])[:10]}.")
    return " ".join(parts)


def edr_line(rec: dict) -> str:
    parts = []
    if rec["name"]:
        parts.append(rec["name"] if rec["opf"] and rec["opf"] in rec["name"] else f"{rec['opf']} {rec['name']}".strip())
    if rec["edrpou"]:
        parts.append(f"ЄДРПОУ {rec['edrpou']}.")
    if rec["stan"]:
        parts.append(f"Стан: {rec['stan']}.")
    founders = [f.split(";")[0].split(" - ")[0].strip() for f in rec["founders"][:4]]
    founders = [f for f in founders if f]
    if founders:
        parts.append("Засновники: " + ", ".join(founders) + ".")
    if rec["statute"]:
        parts.append("Статут: " + rec["statute"] + ".")
    return " ".join(parts)


def vat_line(rec: dict) -> str:
    name = rec.get("name", "")
    kod = rec.get("kod_pdv", "")
    date = rec.get("dat_reestr", "")
    if not name:
        return ""
    return f"{name}. Платник податку на додану вартість, реєстрація {date or 'невідома'} (ІПН {kod})." if kod else f"{name}."


def clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    return line if 20 <= len(line) <= 600 else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edrsr-parquet", action="append", default=[], help="glob patterns of EDRSR parquet parts")
    ap.add_argument("--texts-parquet", action="append", default=[], help="glob patterns of full-text parquet shards")
    ap.add_argument("--edr-uo", help="UO.zip from the EDR register")
    ap.add_argument("--vat", help="pdv_actual.csv")
    ap.add_argument("--edrsr-limit", type=int, default=1_000_000)
    ap.add_argument("--edr-limit", type=int, default=1_200_000)
    ap.add_argument("--vat-limit", type=int, default=200_000)
    ap.add_argument("--output", required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".raw")
    stats = {}
    total = 0
    raw_handle = raw.open("w", encoding="utf-8")

    def push(line: str) -> None:
        nonlocal total
        line = clean_line(line)
        if not line:
            return
        raw_handle.write(line + "\n")
        total += 1

    if args.edrsr_parquet:
        import glob as globlib
        import pyarrow.parquet as pq
        files = []
        for pattern in args.edrsr_parquet:
            files.extend(globlib.glob(pattern))
        count = 0
        for path in files:
            pf = pq.ParquetFile(path)
            columns = [c for c in ("court", "case_number", "category", "judge", "decision_date") if c in pf.schema_arrow.names]
            for batch in pf.iter_batches(batch_size=5000, columns=columns):
                for row in batch.to_pylist():
                    line = edrsr_line(row)
                    if line:
                        push(line)
                        count += 1
                        if count >= args.edrsr_limit:
                            break
                if count >= args.edrsr_limit:
                    break
            if count >= args.edrsr_limit:
                break
        stats["edrsr"] = count

    if args.texts_parquet:
        import glob as globlib
        import pyarrow.parquet as pq
        files = []
        for pattern in args.texts_parquet:
            files.extend(globlib.glob(pattern))
        count = 0
        for path in files:
            pf = pq.ParquetFile(path)
            columns = [c for c in ("court", "case_number", "category", "judge", "text") if c in pf.schema_arrow.names]
            for batch in pf.iter_batches(batch_size=200, columns=columns):
                for row in batch.to_pylist():
                    text = (row.get("text") or "").strip()
                    if len(text) < 200:
                        continue
                    head = " ".join(x for x in (
                        f"Суд: {row['court']}." if row.get("court") else "",
                        f"Справа № {row['case_number']}." if row.get("case_number") else "",
                        f"Категорія: {row['category']}." if row.get("category") else "",
                    ) if x)
                    push(clean_line(head + " " + text[:2500]))
                    count += 1
        stats["edrsr_texts"] = count

    if args.edr_uo:
        count = 0
        for rec in iter_edr_uo(args.edr_uo):
            line = edr_line(rec)
            if line:
                push(line)
                count += 1
            if count >= args.edr_limit:
                break
        stats["edr"] = count

    if args.vat:
        count = 0
        for rec in iter_vat_csv(args.vat):
            line = vat_line(rec)
            if line:
                push(line)
                count += 1
            if count >= args.vat_limit:
                break
        stats["vat"] = count

    raw_handle.close()

    # External dedup + deterministic shuffle-free sampling: exact duplicates
    # removed by sort; a stride sample keeps memory flat.
    import subprocess
    subprocess.run(["sort", "-u", "-o", str(raw), str(raw)], check=True)
    deduped = sum(1 for _ in raw.open("r", encoding="utf-8"))
    stride = max(1, deduped // 1_600_000)
    with raw.open("r", encoding="utf-8") as src, out.open("w", encoding="utf-8") as dst:
        for index, line in enumerate(src):
            if index % stride == 0:
                dst.write(line)
    raw.unlink(missing_ok=True)
    final = sum(1 for _ in out.open("r", encoding="utf-8"))
    print(json.dumps({"written": total, "deduped": deduped, "lines": final, "sources": stats,
                      "bytes": out.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
