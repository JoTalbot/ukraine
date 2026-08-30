#!/usr/bin/env python3
"""Build and query cross-dataset entity links for Ukrainian open data.

Entities are people and organizations identified by public registers:

- ``edrpou``  — 8-digit identifier of legal entities (ЄДРПОУ)
- ``ipn``     — 10-digit individual tax number (ІПН / РНОКПП)
- ``name``    — normalized full name / organization name (weak key)

Links (edges) come from records that reference several entities at once:

- ЄДР founders / signers            -> person~company edges
- ЄДРСР decision texts              -> co-litigant company edges (whitelisted)
- notary registers                  -> notary~office edges
- any record naming several entities -> co_mention edges

Privacy: only identifiers and names already published in the linked open
registers are used; source anonymization is never reversed.

Usage:
    python scripts/entity_links.py build  --edr UO.zip --vat pdv.csv \
        --xml-register notaries=17.zip [--encoding cp1251] \
        [--edrsr-parquet '2026/part-*.parquet'] --db links.db
    python scripts/entity_links.py search --db links.db --id 14359609
    python scripts/entity_links.py search --db links.db --name "Іваненко"
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

EDRPOU_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
IPN_RE = re.compile(r"(?<!\d)(\d{10})(?!\d)")
NAME_SPLIT_RE = re.compile(r"[;|]")

DDL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    value TEXT NOT NULL,
    title TEXT,
    UNIQUE(type, value)
);
CREATE TABLE IF NOT EXISTS mentions (
    mention_id INTEGER PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(entity_id),
    dataset TEXT NOT NULL,
    record_ref TEXT,
    name TEXT,
    extra TEXT
);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON mentions(entity_id, dataset);
CREATE TABLE IF NOT EXISTS edges (
    a INTEGER NOT NULL REFERENCES entities(entity_id),
    b INTEGER NOT NULL REFERENCES entities(entity_id),
    kind TEXT NOT NULL,
    dataset TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (a, b, kind, dataset)
);
CREATE INDEX IF NOT EXISTS idx_edges_a ON edges(a);
CREATE INDEX IF NOT EXISTS idx_edges_b ON edges(b);
"""


# ---------------------------------------------------------------- helpers

def normalize_name(value: str) -> str:
    value = (value or "").replace("ʼ", "'").replace("’", "'")
    value = re.sub(r"\s+", " ", value).strip().upper()
    return value


# Sentinel names published by registers when a person is not identified.
SENTINEL_NAMES = {
    "НЕВИЗНАЧЕНА ФІЗИЧНА ОСОБА",
    "НЕВИЗНАЧЕНА ОСОБА",
    "ФІЗИЧНІ ОСОБИ",
    "ФІЗИЧНА ОСОБА",
    "ІНШІ ФІЗИЧНІ ОСОБИ",
}


def looks_like_date(digits: str) -> bool:
    """Heuristic: 8 digits that read as DDMMYYYY are not an EDRPOU."""
    if len(digits) != 8:
        return False
    day, month, year = int(digits[:2]), int(digits[2:4]), int(digits[4:])
    return 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2035


def extract_edrpou_codes(text: str, whitelist: set[str] | None = None) -> list[str]:
    """8-digit codes from free text; dates excluded; whitelist applied when given."""
    out = []
    for match in EDRPOU_RE.findall(text or ""):
        if looks_like_date(match):
            continue
        if whitelist is not None and match not in whitelist:
            continue
        if match not in out:
            out.append(match)
    return out


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def parse_person_role(text: str) -> tuple[str, str]:
    """'ПІБ - посада' / 'ПІБ; частка - 100 грн' -> (name, role)."""
    name = NAME_SPLIT_RE.split(text)[0]
    role = ""
    if " - " in text:
        candidate = text.split(" - ", 1)[1].strip()
        if not candidate[:1].isdigit():
            role = candidate
    name = name.split(" - ")[0].strip(" ,;:")
    return name, role


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(path)
        self.db.executescript(DDL)
        self._cache: dict[tuple[str, str], int] = {}

    def entity(self, etype: str, value: str, title: str | None = None) -> int:
        value = value.strip()
        key = (etype, value)
        if key in self._cache:
            if title:
                self.db.execute("UPDATE entities SET title=? WHERE entity_id=? AND (title IS NULL OR title='')",
                                (title, self._cache[key]))
            return self._cache[key]
        row = self.db.execute("SELECT entity_id FROM entities WHERE type=? AND value=?", key).fetchone()
        if row:
            self._cache[key] = row[0]
            return row[0]
        cur = self.db.execute("INSERT INTO entities(type, value, title) VALUES(?,?,?)", (etype, value, title))
        self._cache[key] = cur.lastrowid
        return cur.lastrowid

    def mention(self, entity_id: int, dataset: str, record_ref: str | None, name: str | None, extra: dict | None = None) -> None:
        self.db.execute("INSERT INTO mentions(entity_id, dataset, record_ref, name, extra) VALUES(?,?,?,?,?)",
                        (entity_id, dataset, record_ref, name, json.dumps(extra, ensure_ascii=False) if extra else None))

    def edge(self, a: int, b: int, kind: str, dataset: str) -> None:
        if a == b:
            return
        a, b = min(a, b), max(a, b)
        self.db.execute(
            "INSERT INTO edges(a, b, kind, dataset, weight) VALUES(?,?,?,?,1) "
            "ON CONFLICT(a, b, kind, dataset) DO UPDATE SET weight = weight + 1",
            (a, b, kind, dataset),
        )

    def commit(self) -> None:
        self.db.commit()


# ---------------------------------------------------------------- sources

def iter_edr_uo(zip_path: str | Path):
    """Stream <SUBJECT> records from the official ЄДР UO.zip (any encoding)."""
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
                        "edrpou": _text(elem.find("EDRPOU")),
                        "name": _text(elem.find("NAME")),
                        "stan": _text(elem.find("STAN")),
                        "founders": [_text(f) for f in elem.findall(".//FOUNDER") if _text(f)],
                        "signers": [_text(s) for s in elem.findall(".//SIGNER") if _text(s)],
                    }
                    root.clear()


def iter_vat_csv(path: str | Path):
    import csv
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            yield {k: (v or "").strip() for k, v in row.items() if k}


def iter_xml_register(zip_path: str | Path, encoding: str = "utf-8"):
    """Generic <RECORD> iterator for XML registers inside a zip (notaries, experts...)."""
    with zipfile.ZipFile(zip_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        with zf.open(member) as raw:
            parser = ET.iterparse(raw, events=("start", "end"))
            root = None
            for event, elem in parser:
                if event == "start" and root is None:
                    root = elem
                if event == "end" and elem.tag.strip().upper().endswith("RECORD"):
                    yield {child.tag.strip().upper(): _text(child) for child in elem}
                    root.clear()


def iter_delimited(path: str | Path, encoding: str = "cp1251", delimiter: str = ";"):
    import csv
    with open(path, newline="", encoding=encoding, errors="replace") as fh:
        for row in csv.DictReader(fh, delimiter=delimiter):
            yield {k: (v or "").strip() for k, v in row.items() if k}


def iter_json_register(path: str | Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("data", data) if isinstance(data, dict) else data
    for row in rows or []:
        if isinstance(row, dict):
            yield row


def detect_register_fields(sample: dict) -> tuple[str | None, str | None]:
    """Pick (person-name, org-name) field names from a register row sample."""
    person = org = None
    for key in sample:
        upper = key.upper()
        if person is None and upper in {"FIO", "PIB", "NAME_PERSON", "FULLNAME", "SECONDNAME"} or (person is None and upper in {"AK_NAME"}):
            person = key
        if org is None and upper in {"NAME_OBJ", "ORGANIZATION", "NAME", "SUBJECT_NAME", "AUDITOR_FIRM"}:
            org = key
    return person, org


# ---------------------------------------------------------------- build

def cmd_build(args: argparse.Namespace) -> None:
    store = Store(args.db)

    # 1) ЄДР spine: EDRPOU entities + person edges from founders/signers.
    edrpou_index: dict[str, int] = {}
    subject_count = 0
    if args.edr:
        for rec in iter_edr_uo(args.edr):
            subject_count += 1
            if not rec["edrpou"] or not rec["edrpou"].isdigit() or set(rec["edrpou"]) == {"0"}:
                continue
            company = store.entity("edrpou", rec["edrpou"], rec["name"] or None)
            edrpou_index[rec["edrpou"]] = company
            store.mention(company, "edr", rec["edrpou"], rec["name"],
                          {"stan": rec["stan"]} if rec["stan"] else None)
            for founder in rec["founders"]:
                name, _role = parse_person_role(founder)
                if not name or EDRPOU_RE.fullmatch(name) or normalize_name(name) in SENTINEL_NAMES:
                    continue
                person = store.entity("name", normalize_name(name), name)
                store.edge(person, company, "founder", "edr")
            for signer in rec["signers"]:
                name, role = parse_person_role(signer)
                if not name or EDRPOU_RE.fullmatch(name) or normalize_name(name) in SENTINEL_NAMES:
                    continue
                person = store.entity("name", normalize_name(name), name)
                store.edge(person, company, "signer", "edr")
            if subject_count % 100_000 == 0:
                store.commit()
                print(f"  ЄДР: {subject_count:,} субъектов…", flush=True)
        store.commit()
        print(f"ЄДР: {subject_count:,} субъектов, {len(edrpou_index):,} з ЄДРПОУ")

    # 2) VAT registry: adaptive identifier prefix (8 for legal, 10 for FOP).
    if args.vat:
        legal = set(edrpou_index)
        hits8 = hits10 = total = 0
        for rec in iter_vat_csv(args.vat):
            total += 1
            kod = re.sub(r"\D", "", rec.get("kod_pdv", "") or rec.get("kod", ""))
            name = rec.get("name", "")
            if len(kod) >= 8 and kod[:8] in legal:
                entity = edrpou_index[kod[:8]]
                hits8 += 1
            elif len(kod) >= 10:
                entity = store.entity("ipn", kod[:10], name)
                hits10 += 1
            elif len(kod) >= 8:
                entity = store.entity("edrpou", kod[:8], name)
                hits8 += 1
            else:
                continue
            store.mention(entity, "vat_payers", kod, name,
                          {"dat_reestr": rec.get("dat_reestr"), "dat_term": rec.get("dat_term")})
        store.commit()
        print(f"ПДВ: {total:,} строк (ЄДРПОУ-совпадений: {hits8:,}; ІПН: {hits10:,})")

    # 3) Generic XML/CSV/JSON registers -> person entities + mentions.
    for spec in args.xml_register or []:
        name, _, path = spec.partition("=")
        for rec in iter_xml_register(path, args.encoding):
            person_field, org_field = detect_register_fields(rec)
            person = org = None
            if person_field and rec.get(person_field):
                person_name = str(rec[person_field])
                if normalize_name(person_name) not in SENTINEL_NAMES:
                    person = store.entity("name", normalize_name(person_name), person_name)
                    store.mention(person, name, rec.get("REG_NUM") or rec.get("LICENSE"), person_name)
            if org_field and rec.get(org_field):
                org = store.entity("name", normalize_name(rec[org_field]), rec[org_field])
            if person and org:
                store.edge(person, org, "works_at", name)
    for spec in args.csv_register or []:
        name, _, path = spec.partition("=")
        sample = next(iter_delimited(path), {})
        person_field, org_field = detect_register_fields(sample)
        for rec in iter_delimited(path):
            person = None
            if person_field and rec.get(person_field):
                person = store.entity("name", normalize_name(rec[person_field]), rec[person_field])
            elif org_field and rec.get(org_field):
                person = store.entity("name", normalize_name(rec[org_field]), rec[org_field])
            if person:
                store.mention(person, name, None, None, {k: v for k, v in rec.items() if k not in (person_field, org_field)})
    for spec in args.json_register or []:
        name, _, path = spec.partition("=")
        for rec in iter_json_register(path):
            person_field, org_field = detect_register_fields(rec)
            if person_field and rec.get(person_field):
                person = store.entity("name", normalize_name(str(rec[person_field])), str(rec[person_field]))
                extra = {k: rec[k] for k in ("edrpou", "ipn", "regNum", "id") if rec.get(k)}
                for key in ("edrpou", "ipn", "id"):
                    val = re.sub(r"\D", "", str(rec.get(key, "") or ""))
                    if len(val) == 8 and val in edrpou_index:
                        store.edge(person, edrpou_index[val], "linked", name)
                    elif len(val) == 10 and rec.get(key):
                        store.edge(person, store.entity("ipn", val), "linked", name)
                store.mention(person, name, str(rec.get("regNum", "") or ""), str(rec[person_field]), extra or None)
    store.commit()

    # 4) ЄДРСР decisions: judge~court edges from decision metadata; when a
    #    decision text is present, whitelisted EDRPOU co-mentions also become
    #    company~company edges.
    if args.edrsr_parquet:
        import glob as globlib
        try:
            import pyarrow.parquet as pq
        except ImportError:
            sys.exit("pyarrow требуется для --edrsr-parquet")
        if not edrpou_index:
            for row_id, row_value in store.db.execute("SELECT entity_id, value FROM entities WHERE type='edrpou'"):
                edrpou_index[row_value] = row_id
        whitelist = set(edrpou_index)
        files = []
        for pattern in args.edrsr_parquet:
            files.extend(globlib.glob(pattern))
        decisions = linked_pairs = 0
        for path in files:
            pf = pq.ParquetFile(path)
            wanted = [c for c in ("text", "case_number", "document_id", "judge", "court") if c in pf.schema_arrow.names]
            for batch in pf.iter_batches(batch_size=5000, columns=wanted):
                for row in batch.to_pylist():
                    decisions += 1
                    ref = row.get("case_number") or row.get("document_id") or ""
                    judge_name = (row.get("judge") or "").strip()
                    court_name = (row.get("court") or "").strip()
                    if judge_name and court_name:
                        judge = store.entity("name", normalize_name(judge_name), judge_name)
                        court = store.entity("name", normalize_name(court_name), court_name)
                        if ref:
                            store.mention(judge, "edrsr", ref, judge_name, {"court": court_name})
                        store.edge(judge, court, "judges_in", "edrsr")
                    text = row.get("text") or ""
                    codes = extract_edrpou_codes(text, whitelist) if text else []
                    if codes:
                        for code in codes:
                            store.mention(edrpou_index[code], "edrsr", ref, None, None)
                        for i in range(len(codes)):
                            for j in range(i + 1, len(codes)):
                                store.edge(edrpou_index[codes[i]], edrpou_index[codes[j]], "co_litigant", "edrsr")
                                linked_pairs += 1
            store.commit()
            print(f"ЄДРСР: {Path(path).name} — решений: {decisions:,}, текстовых рёбер: {linked_pairs:,}")

    stats = store.db.execute(
        "SELECT (SELECT COUNT(*) FROM entities), (SELECT COUNT(*) FROM mentions), (SELECT COUNT(*) FROM edges)"
    ).fetchone()
    store.commit()
    print(f"Готово: entities={stats[0]:,}, mentions={stats[1]:,}, edges={stats[2]:,} -> {args.db}")


# ---------------------------------------------------------------- search

def resolve_entity(db: sqlite3.Connection, identifier: str | None, name: str | None):
    if identifier:
        digits = re.sub(r"\D", "", identifier)
        if len(digits) == 8:
            row = db.execute("SELECT * FROM entities WHERE type='edrpou' AND value=?", (digits,)).fetchone()
            if row:
                return row
        elif len(digits) == 10:
            row = db.execute("SELECT * FROM entities WHERE type='ipn' AND value=?", (digits,)).fetchone()
            if row:
                return row
        elif len(digits) >= 12:
            for candidate in (digits[:8], digits[:10]):
                row = db.execute("SELECT * FROM entities WHERE value=?", (candidate,)).fetchone()
                if row:
                    return row
        return db.execute("SELECT * FROM entities WHERE value LIKE ?", (f"%{digits}%",)).fetchone()
    if name:
        needle = normalize_name(name)
        return db.execute(
            "SELECT * FROM entities WHERE type='name' AND value LIKE ? ORDER BY LENGTH(value) LIMIT 1",
            (f"%{needle}%",),
        ).fetchone()
    return None


def cmd_search(args: argparse.Namespace) -> None:
    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    entity = resolve_entity(db, args.id, args.name)
    if entity is None:
        print("Ничего не найдено.")
        return
    eid = entity["entity_id"]
    print(f"=== {entity['title'] or entity['value']}  [{entity['type']}: {entity['value']}]")

    print("\n-- Упоминания в базах --")
    for row in db.execute(
        "SELECT dataset, COUNT(*) n, MIN(name) sample FROM mentions WHERE entity_id=? GROUP BY dataset ORDER BY n DESC", (eid,)
    ):
        print(f"   {row['dataset']:22s} {row['n']:>6,}   например: {(row['sample'] or '')[:60]}")

    def neighbours(root: int, depth: int):
        frontier = {root}
        seen = {root}
        result = []
        for _ in range(depth):
            nxt = set()
            for node in frontier:
                for row in db.execute(
                    "SELECT b, kind, dataset, weight FROM edges WHERE a=? "
                    "UNION SELECT a, kind, dataset, weight FROM edges WHERE b=?", (node, node)
                ):
                    other = row[0]
                    if other not in seen:
                        seen.add(other)
                        nxt.add(other)
                        result.append((other, row[1], row[2], row[3]))
            frontier = nxt
        return result

    print("\n-- Связи (сущности, встречающиеся вместе) --")
    rows = neighbours(eid, args.depth)
    for other, kind, dataset, weight in sorted(rows, key=lambda r: -r[3])[:args.limit]:
        info = db.execute("SELECT type, value, title FROM entities WHERE entity_id=?", (other,)).fetchone()
        title = (info["title"] or info["value"]) if info else "?"
        print(f"   [{kind}/{dataset}] {weight:>3}x  {title[:70]}  ({info['type']}: {info['value']})" if info else "")
    print(f"\nВсего связанных сущностей (глубина {args.depth}): {len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--db", required=True)
    build.add_argument("--edr", help="UO.zip из ЄДР (спина графа)")
    build.add_argument("--vat", help="pdv_actual.csv")
    build.add_argument("--xml-register", action="append", help="name=path.zip (RECORD-XML)")
    build.add_argument("--csv-register", action="append", help="name=path.csv")
    build.add_argument("--json-register", action="append", help="name=path.json")
    build.add_argument("--edrsr-parquet", action="append", help="glob паркет-частей ЄДРСР")
    build.add_argument("--encoding", default="utf-8", help="кодировка XML-реестров")
    build.set_defaults(func=cmd_build)

    search = sub.add_parser("search")
    search.add_argument("--db", required=True)
    search.add_argument("--id", help="ЄДРПОУ / ІПН / ПДВ-номер")
    search.add_argument("--name", help="ФИО или название")
    search.add_argument("--depth", type=int, default=1)
    search.add_argument("--limit", type=int, default=30)
    search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
