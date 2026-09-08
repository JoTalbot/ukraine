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
    python scripts/entity_links.py inspect wanted_fugitives.csv   # confirm person columns
    python scripts/entity_links.py add-people --db links.db \
        --json-register wanted_fugitives=w.json --zipcsv-register debtors=d.zip
    python scripts/entity_links.py search --db links.db --id 14359609
    python scripts/entity_links.py search --db links.db --name "Іваненко"

Person↔register mapping lives in config/person_register_map.json (see
docs/PEOPLE_BASES.md): person-subject bases resolve people to a shared РНОКПП
identity so one person is traceable across bases.
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


def _xlsx_sheets():
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - env-specific
        raise ImportError("xlsx-реестры требуют openpyxl (pip install openpyxl)") from exc
    return load_workbook


def iter_xlsx_register(path: str | Path, sheet: str | None = None):
    """Stream rows of an xlsx register as dicts (first row = header).

    Sheet selection mirrors how real registers keep the dataset in a specific
    tab (e.g. many xlsx publications carry a codebook on the first sheet). A
    ``sheet`` name may be declared per-register in ``config/person_register_map.json``.
    """
    wb = _xlsx_sheets()(path, read_only=True, data_only=True)
    target = sheet if sheet in (wb.sheetnames or []) else (wb.sheetnames or [None])[0]
    if target is None:
        return
    ws = wb[target]
    header = None
    for raw in ws.iter_rows(values_only=True):
        values = [("" if c is None else str(c).strip()) for c in raw]
        if header is None:
            header = values
            continue
        row = {h: v for h, v in zip(header, values) if h}
        if row:
            yield row
    wb.close()


def iter_zip_csv(path: str | Path, encoding: str = "cp1251", delimiter: str = ";"):
    """Stream rows of a ``name.csv`` inside a zip (e.g. Єдиний реєстр боржників).

    Real mirrors ship large CSVs zipped; only the in-memory member bytes are
    decompressed as they are read, so multi-GB members stream without full load.
    """
    import csv
    import io
    with zipfile.ZipFile(path) as zf:
        member = max((n for n in zf.namelist() if n.lower().endswith(".csv")),
                     key=lambda n: zf.getinfo(n).file_size)
        with zf.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding=encoding, errors="replace", newline="")
            for row in csv.DictReader(text, delimiter=delimiter):
                yield {k: (v or "").strip() for k, v in row.items() if k}


def detect_register_fields(sample: dict) -> tuple[str | None, str | None]:
    """Pick (person-name, org-name) field names from a register row sample."""
    person = org = None
    for key in sample:
        upper = key.upper()
        if (person is None and upper in {"FIO", "PIB", "NAME_PERSON", "FULLNAME", "SECONDNAME"}) or (person is None and upper == "AK_NAME"):
            person = key
        if org is None and upper in {"NAME_OBJ", "ORGANIZATION", "NAME", "SUBJECT_NAME", "AUDITOR_FIRM"}:
            org = key
    return person, org


# ------------------------------------------------------------------------
# Person identity spine.
#
# People appear in many registers, but each register names them differently
# and only some registers publish the stable 10-digit РНОКПП / ІПН (individual
# tax number). To link the *same person* across bases we therefore:
#
#   * keep the display `name` entity as it is written in a register, and
#   * when the register publishes a РНОКПП, create one `ipn` identity entity
#     and connect every written name to it with an `identity` edge.
#
# The `ipn` identity is then the shared hub: a person who is a ФОП (in ЄДР/ПДВ),
# a debtor, a wanted person and a sanction subject in different bases resolves
# to the same card through their tax number — that card answers "in which bases
# is this person, and how is each connected to the organisation graph?".
#
# Only identifiers and names lawfully published in the linked open registers
# are used; source anonymization is never reversed (no_deanonymization).

DEFAULT_PEOPLE_MAP = Path(__file__).resolve().parent.parent / "config" / "person_register_map.json"

# Edge kinds that connect a *person* to an *organisation* (role on the edge).
PERSON_ORG_KINDS = {"founder", "signer", "works_at", "linked", "beneficial_owner", "listed_in"}
# Edge kind that declares a written name to be an alias of a РНОКПП identity.
IDENTITY_EDGE = "identity"


def digits_of(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm_header(key: str) -> str:
    return re.sub(r"[\s_\-'/ʼ’().,\"]", "", (key or "").upper())


# Keyword fragments used only to *guess* a column when a register mapping does
# not declare it explicitly (also powers `entity_links.py inspect`).
_NAME_MARKERS = {"FIO", "PIB", "ФІО", "ПІБ", "ФИО", "NAME_PERSON", "FULLNAME", "SECONDNAME", "AK_NAME", "PERSON"}
_NAME_PREFIX_MARKERS = ("ПРІЗВИЩЕ", "ФАМІЛІЯ", "ФАМИЛИЯ", "SURNAME", "LASTNAME", "ІМ", "ИМЯ")
_IPN_MARKERS = {"IPN", "ІПН", "ІНН", "ИНН", "INN", "TIN", "DRFO", "ДРФО", "РНОКПП", "RNOKPP"}
_EDRPOU_MARKERS = {"EDRPOU", "ЄДРПОУ", "ЕДРПОУ"}
_ORG_MARKERS = {"NAME_OBJ", "ORGANIZATION", "ORG", "SUBJECT_NAME", "AUDITOR_FIRM", "НАЗВА", "НАЗВА_ОРГ", "NAME", "ORG_NAME"}
_ORG_CONTAINS = ("НАЗВА ОРГАНІЗАЦІЇ", "НАЗВА СУБ", "НАЗВА_ЮР", "ФІРМА")
_REG_MARKERS = {"REG_NUM", "REG_NUMBER", "LICENSE", "СВІДОЦТВО", "СВІДОЦТВА"}
_REG_CONTAINS = ("РЕЄСТРАЦІЙНИЙ НОМЕР", "НОМЕР СВІДОЦТВА", "НОМЕР РЕЄСТРУ", "№ РЕЄСТРУ")


def guess_field(row: dict, exact_markers: set[str], prefix_markers=(), contains=()) -> str | None:
    """Return the key of the first row field whose header matches a marker set."""
    for key, value in row.items():
        if value is None or str(value).strip() == "":
            continue
        nk = _norm_header(key)
        if nk in exact_markers:
            return key
        if prefix_markers and any(nk.startswith(m) for m in prefix_markers):
            return key
        if contains and any(c in key.upper() for c in contains):
            return key
    return None


def canonical_fields(row: dict) -> dict:
    """Best-effort mapping of a register row into canonical person/identity slots.

    Returns a dict with keys ``person``, ``ipn``, ``edrpou``, ``org``, ``regnum``.
    ``person``/``org`` are the raw written values; ``ipn``/``edrpou`` are clean
    digit strings ('' when absent). This is a *heuristic* for diagnostics and
    fallback; production registers should declare explicit columns via
    `config/person_register_map.json` so aliases are unambiguous.
    """
    row = {k: (str(v).strip() if v is not None else "") for k, v in row.items() if v is not None}
    out: dict[str, str] = {"person": "", "ipn": "", "edrpou": "", "org": "", "regnum": ""}

    person_key = guess_field(row, _NAME_MARKERS, _NAME_PREFIX_MARKERS)
    ipn_key = guess_field(row, _IPN_MARKERS)
    edrpou_key = guess_field(row, _EDRPOU_MARKERS)
    org_key = guess_field(row, _ORG_MARKERS, contains=_ORG_CONTAINS)
    reg_key = guess_field(row, _REG_MARKERS, contains=_REG_CONTAINS)

    if person_key:
        out["person"] = row[person_key]
    if ipn_key:
        code = digits_of(row[ipn_key])
        out["ipn"] = code if len(code) == 10 else ""
    if edrpou_key:
        code = digits_of(row[edrpou_key])
        out["edrpou"] = code if len(code) == 8 else ""
    if org_key:
        out["org"] = row[org_key]
    if reg_key:
        out["regnum"] = row[reg_key]

    # Fall back on numeric-value length classification (robust across headers):
    # 10 digits -> person tax number, 8 digits -> ЄДРПОУ (unless a date-like
    # code), 12+ digits -> a ПДВ number whose prefix is a person/company code.
    if not out["ipn"] or not out["edrpou"]:
        for key, value in row.items():
            if key in (person_key, ipn_key, edrpou_key, org_key, reg_key):
                continue
            code = digits_of(value)
            if not out["ipn"] and len(code) == 10:
                out["ipn"] = code
            elif not out["edrpou"] and len(code) == 8 and not looks_like_date(code):
                out["edrpou"] = code
            elif not out["ipn"] and not out["edrpou"] and len(code) >= 12:
                if looks_like_date(code[:8]):
                    continue
                out["edrpou"] = code[:8] if code[:8] in _EDRPOU_CACHE else out["edrpou"]
    return out


# Populated during build (set of known ЄДРПОУ). Used to disambiguate 8-digit
# codes that appear in free-form numeric columns.
_EDRPOU_CACHE: set[str] = set()


def load_people_map(path: str | Path | None) -> dict:
    """Load the person↔register mapping (see ``config/person_register_map.json``)."""
    chosen = Path(path) if path else DEFAULT_PEOPLE_MAP
    if not chosen.exists():
        return {}
    data = json.loads(chosen.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "registers" in data:
        return data["registers"]
    return data if isinstance(data, dict) else {}


def _row_value_by_aliases(row: dict, aliases) -> str:
    """Return the first non-empty cell for a list of column aliases."""
    for alias in aliases or []:
        key = str(alias)
        if key in row and row[key] not in (None, ""):
            return str(row[key]).strip()
        for actual, value in row.items():
            if value in (None, ""):
                continue
            if _norm_header(actual) == _norm_header(key):
                return str(value).strip()
    return ""


def ingest_person_rows(store: Store, register_id: str, desc: dict, rows, edrpou_index: dict[str, int]) -> dict:
    """Link person-subject rows of one register into the identity graph.

    A person is the row subject when the register lists individuals themselves
    (advocates, court experts, arbitration managers, wanted/missing persons,
    sanction subjects, debtors, beneficial owners). Each such person becomes:

      * a ``name`` entity as written (display),
      * an ``ipn`` identity entity when the register publishes a РНОКПП,
        connected to the name by an ``identity`` edge,
      * a ``mention`` in the register on both entities, and
      * an edge person→organisation when the row also references a company
        (by ЄДРПОУ or a company name).

    Returns dict of counters (``rows``, ``people``, ``identities``, ``org_edges``).
    """
    fields = desc.get("fields") or {}
    aliases = {slot: (fields.get(slot) or []) for slot in ("ipn", "edrpou", "org", "regnum")}
    person_aliases = fields.get("person") or []
    # Multi-column name registers split a full name into parts
    # (e.g. wanted_fugitives: LAST_NAME_U/FIRST_NAME_U/MIDDLE_NAME_U). Declared as
    # fields.person_parts = [[alt...], [alt...], ...]; the row's name is the parts
    # joined in order (each part = first non-empty cell among its aliases).
    person_parts = fields.get("person_parts") or []
    org_edge = desc.get("org_edge") or "linked"
    extra_fields = desc.get("extra_fields") or []
    mixed = desc.get("subject") == "mixed"
    # Code-length mode: some registers (e.g. Єдиний реєстр боржників) put the
    # person's ORG name in ONE column and identify org-vs-person only by the
    # length of a shared ID column: 10 digits -> individual (РНОКПП), 8 digits
    # -> legal entity (ЄДРПОУ). Declared as fields {"name":[...], "id":[...]}.
    id_aliases = fields.get("id") or []
    name_aliases = fields.get("name") or []
    code_mode = bool(id_aliases and name_aliases)
    counters = {"rows": 0, "people": 0, "identities": 0, "org_edges": 0, "org_subjects": 0}

    for raw in rows:
        row = {str(k): ("" if v is None else str(v).strip()) for k, v in raw.items()}
        if not row:
            continue
        counters["rows"] += 1

        if person_parts:
            parts = [_row_value_by_aliases(row, grp) for grp in person_parts]
            person_text = " ".join(p for p in parts if p)
        else:
            person_text = _row_value_by_aliases(row, person_aliases)
        ipn = digits_of(_row_value_by_aliases(row, aliases["ipn"]))
        edrpou = digits_of(_row_value_by_aliases(row, aliases["edrpou"]))
        org_text = _row_value_by_aliases(row, aliases["org"])
        regnum = _row_value_by_aliases(row, aliases["regnum"])

        if code_mode:
            code = digits_of(_row_value_by_aliases(row, id_aliases))
            cell = _row_value_by_aliases(row, name_aliases)
            if len(code) == 10:
                person_text, ipn, edrpou, org_text = cell, code, "", ""
            elif len(code) == 8 and not looks_like_date(code):
                person_text, ipn, edrpou, org_text = "", "", code, cell
            else:
                person_text, ipn, edrpou, org_text = cell, "", "", ""

        # Identifiers are taken ONLY from explicit aliases. A generic numeric
        # scan is deliberately avoided here so that unrelated 10/8-digit columns
        # (registration numbers, phones, case ids) are never mistaken for РНОКПП
        # or ЄДРПОУ. Registers that do publish them declare the column explicitly.

        if len(ipn) != 10:
            ipn = ""
        if len(edrpou) != 8 or looks_like_date(edrpou):
            edrpou = ""
        if person_text and normalize_name(person_text) in SENTINEL_NAMES:
            person_text = ""
        if not person_text and not ipn:
            # No person in this row. In a *mixed* register the row subject may be
            # a legal entity — record it as an org mention so it stays reachable
            # through the company spine (sanctions/debtors list both kinds).
            if mixed and (edrpou or org_text):
                org_ent = None
                if edrpou and edrpou in edrpou_index:
                    org_ent = edrpou_index[edrpou]
                elif edrpou:
                    org_ent = store.entity("edrpou", edrpou, org_text or None)
                elif org_text and normalize_name(org_text) not in SENTINEL_NAMES:
                    org_ent = store.entity("name", normalize_name(org_text), org_text)
                if org_ent is not None:
                    extra = None
                    if extra_fields:
                        extra = {a: row[a] for a in extra_fields if row.get(a) not in (None, "")} or None
                    store.mention(org_ent, register_id, regnum or None, org_text or None, extra)
                    counters["org_subjects"] += 1
            continue

        extra = None
        if extra_fields:
            extra = {a: row[a] for a in extra_fields if row.get(a) not in (None, "")} or None

        name_ent = store.entity("name", normalize_name(person_text), person_text) if person_text else None
        ipn_ent = None
        if ipn:
            ipn_ent = store.entity("ipn", ipn, person_text or None)
            store.mention(ipn_ent, register_id, regnum or None, person_text or None, extra)
            counters["identities"] += 1
            if name_ent is not None and name_ent != ipn_ent:
                store.edge(name_ent, ipn_ent, IDENTITY_EDGE, register_id)
        if name_ent is not None:
            store.mention(name_ent, register_id, regnum or None, person_text, extra)
            counters["people"] += 1

        # Link to an organisation when the row co-references one.
        subject = ipn_ent if ipn_ent is not None else name_ent
        if subject is not None:
            target = None
            if edrpou and edrpou in edrpou_index:
                target = edrpou_index[edrpou]
            elif edrpou:
                target = store.entity("edrpou", edrpou, org_text or None)
            elif org_text:
                normalized = normalize_name(org_text)
                if normalized not in SENTINEL_NAMES and normalized != normalize_name(person_text or ""):
                    target = store.entity("name", normalized, org_text)
            if target is not None:
                store.edge(subject, target, org_edge if org_edge in PERSON_ORG_KINDS else "linked", register_id)
                counters["org_edges"] += 1
    return counters


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
                name, _role = parse_person_role(signer)
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

    # 3) XML/CSV/JSON registers. Person-subject bases (declared in
    #    config/person_register_map.json) build identity-linked people; the
    #    remaining registers keep the generic person/org mention behaviour.
    people_map = load_people_map(getattr(args, "people_map", None))
    _EDRPOU_CACHE.update(edrpou_index)

    def person_path(name: str) -> dict | None:
        desc = people_map.get(name)
        return desc if desc and desc.get("subject") in ("person", "mixed") else None

    for spec in args.xml_register or []:
        name, _, path = spec.partition("=")
        desc = person_path(name)
        if desc:
            counts = ingest_person_rows(store, name, desc, iter_xml_register(path, args.encoding), edrpou_index)
            store.commit()
            print(f"{name}: {counts['rows']:,} строк, людей: {counts['people']:,}, РНОКПП: {counts['identities']:,}, связей с орг: {counts['org_edges']:,}")
            continue
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
        desc = person_path(name)
        if desc:
            counts = ingest_person_rows(store, name, desc, iter_delimited(path), edrpou_index)
            store.commit()
            print(f"{name}: {counts['rows']:,} строк, людей: {counts['people']:,}, РНОКПП: {counts['identities']:,}, связей с орг: {counts['org_edges']:,}")
            continue
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
        desc = person_path(name)
        if desc:
            counts = ingest_person_rows(store, name, desc, iter_json_register(path), edrpou_index)
            store.commit()
            print(f"{name}: {counts['rows']:,} строк, людей: {counts['people']:,}, РНОКПП: {counts['identities']:,}, связей с орг: {counts['org_edges']:,}")
            continue
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

    # 3b) xlsx / zip-of-csv registers. These formats are used for person-subject
    #     bases (sanctions .xlsx, debtors .zip>csv). Only registers declared in
    #     config/person_register_map.json are consumed; anything else is skipped.
    for fmt, spec, iterator in [
        ("xlsx", s, lambda p, s_, d: iter_xlsx_register(p, d.get("sheet")) if d else iter_xlsx_register(p))
        for s in args.xlsx_register or []
    ] + [
        ("zipcsv", s, lambda p, s_, d: iter_zip_csv(p))
        for s in args.zipcsv_register or []
    ]:
        name, _, path = spec.partition("=")
        desc = person_path(name)
        if not desc:
            print(f"{name}: не объявлен в person_register_map.json — пропуск (формат {fmt})")
            continue
        if desc.get("enabled") is False:
            print(f"{name}: помечен enabled=false ({desc.get('enabled_reason') or 'см. маппинг'}) — пропуск")
            continue
        counts = ingest_person_rows(store, name, desc, iterator(path, None, desc), edrpou_index)
        store.commit()
        print(f"{name}: {counts['rows']:,} строк, людей: {counts['people']:,}, РНОКПП: {counts['identities']:,}, связей с орг: {counts['org_edges']:,}")
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


# ---------------------------------------------------------------- name resolution
#
# Name-only people (wanted/missing/professional registers that publish no РНОКПП)
# are stored as `name` entities. To still connect the *same person* that appears
# in a name-only base AND in a base that publishes РНОКПП (debtors, ФОП/ПДВ), we
# try to resolve a person-like name entity to an `ipn` identity entity.
#
# This is inherently heuristic, so it is deliberately CONSERVATIVE:
#   * only `name` entities that look like a natural person are considered;
#   * resolution requires an EXACT surname and a strong given-name/patronymic
#     agreement (full or unambiguous initial);
#   * a candidate is accepted only when the best match is clearly better than
#     the runner-up (unique argmax above min-score);
#   * matched edges are kind=`identity`, dataset=`name_resolve` so they can be
#     audited and removed independently (`DELETE FROM edges WHERE dataset=
#     'name_resolve'`) without touching register-sourced identity edges.
# This never creates new identifiers and never reverses source anonymization.

# Token separators include apostrophes found in Ukrainian registers (В'ЯЧЕСЛАВ).
_TOKEN_RE = re.compile(r"[A-ZА-ЯЄІЇҐ]+", re.UNICODE)
_APOS = re.compile(r"['ʼ’`]")

# Organisation indicators: a `name` entity containing these is not a person.
_ORG_KEYWORDS = {
    "ТОВ", "ТОВАРИСТВО", "ПАТ", "ПУБЛІЧНЕ", "ПРИВАТНЕ", "ПП", "АКЦІОНЕРНЕ",
    "КОМАНДИТНЕ", "ДОДАТКОВА", "КОМПАНІЯ", "КОНЦЕРН", "ХОЛДИНГ", "КОРПОРАЦІЯ",
    "ФІРМА", "БАНК", "УНІВЕРСИТЕТ", "ІНСТИТУТ", "АКАДЕМІЯ", "КОЛЕДЖ", "ШКОЛА",
    "УПРАВЛІННЯ", "ДЕПАРТАМЕНТ", "МІНІСТЕРСТВО", "СЛУЖБА", "РАДА", "СУД",
    "ПРОКУРАТУРА", "ПОЛІЦІЯ", "КЛІНІЧНЕ", "БЮРО", "ЦЕНТР", "ФОНД", "ЗАВОД",
    "ФАБРИКА", "КОМБІНАТ", "АСОЦІАЦІЯ", "СПІЛКА", "ГРОМАДСЬКЕ", "ОБ'ЄДНАННЯ",
    "ФІЛІЯ", "ПРЕДСТАВНИЦТВО", "АГЕНТСТВО", "КООПЕРАТИВ", "НАЦІОНАЛЬНИЙ",
    "ДЕРЖАВНИЙ", "ДЕРЖАВНА", "МІСЬКИЙ", "РАЙОННИЙ", "ОБЛАСНИЙ", "УКРАЇНИ",
    "КИЇВСЬКИЙ", "КИЇВСЬКА", "НОТАРІАЛЬНА", "КОНТОРА", "АПЕЛЯЦІЙНИЙ",
    "АДМІНІСТРАТИВНИЙ", "ГОСПОДАРСЬКИЙ", "ВИЩИЙ", "ОКРУЖНИЙ", "КАСАЦІЙНИЙ",
    "ВЕРХОВНИЙ", "КРИМІНАЛЬНИЙ", "ЦИВІЛЬНИЙ", "ЕКСПЕРТНЕ", "УСТАНОВА",
    "ЗАКЛАД", "ОРГАНІЗАЦІЯ", "ОБ'ЄДНАННЯ", "ГРОМАДСЬКА",
}


def _name_tokens(value: str) -> list[str]:
    return _TOKEN_RE.findall(_APOS.sub("", value or "").upper())


def is_person_like_name(value: str) -> bool:
    """Conservative check that a normalized `name` looks like a natural person.

    Person full names are typically 2-4 upper-case words with no legal-form,
    place or institution keywords and no digits.
    """
    value = _APOS.sub("", (value or "")).upper()
    toks = _TOKEN_RE.findall(value)
    joined = " ".join(toks)
    if len(toks) < 2 or len(toks) > 4:
        return False
    if any(t in _ORG_KEYWORDS for t in toks):
        return False
    if re.search(r"\d", value):
        return False
    # Heuristic: the last token usually carries a patronymic marker (…ович,
    # …івна, …ич, …на) for a full Ukrainian name; require it for 3-token names.
    if len(toks) == 3 and not re.search(r"(ОВИЧ|ЄВИЧ|ІВНА|ЇВНА|ІВИЧ|ОВНА|ИЧ|ВИЧ|ВНА)$", toks[-1]):
        return False
    return bool(joined)


def _name_agreement(a: str, b: str) -> float | None:
    """Similarity of two single name tokens (surname/given/patronymic).

    Returns a weight in [0,1] or None when they can't agree at all.
      - exact                -> 1.0
      - full vs initial      -> 0.9  (ПЕТРО ~ П. / П. ~ ПЕТРО)
      - initials equal       -> 0.85 (П. ~ П. as separate tokens)
    Tokens are compared after removing apostrophes and dots.
    """
    a = _APOS.sub("", a or "").upper().replace(".", "")
    b = _APOS.sub("", b or "").upper().replace(".", "")
    if not a or not b:
        return None
    if a == b:
        return 1.0
    a_single = len(a) == 1 and a.isalpha()
    b_single = len(b) == 1 and b.isalpha()
    if a_single and b_single:
        return 0.85 if a == b else None
    if a_single and not b_single:
        return 0.9 if a == b[0] else None
    if b_single and not a_single:
        return 0.9 if b == a[0] else None
    return None


def score_person_name(name_tokens: list[str], ipn_tokens: list[str]) -> float | None:
    """Score name_tokens against ipn_tokens (both surname-first). None if not a candidate.

    Rules:
      - surname (token 0) must agree exactly;
      - given name (token 1) must agree (exact or unambiguous initial);
      - patronymic (token 2): when present on BOTH sides it must agree; when
        present on one side only it is a soft positive (partial information).
    """
    if len(name_tokens) < 2 or len(ipn_tokens) < 2:
        return None
    if _name_agreement(name_tokens[0], ipn_tokens[0]) != 1.0:
        return None
    given = _name_agreement(name_tokens[1], ipn_tokens[1])
    if given is None:
        return None

    score = 0.5 + 0.35 * given  # surname fixed (0.5) + given (up to 0.85)
    nt3 = name_tokens[2] if len(name_tokens) > 2 else None
    it3 = ipn_tokens[2] if len(ipn_tokens) > 2 else None
    if nt3 and it3:
        pat = _name_agreement(nt3, it3)
        if pat is None:
            return None  # both claim a different patronymic -> different person
        score += 0.15 * pat
    elif nt3 or it3:
        score += 0.05  # partial patronymic known on one side only
    return min(score, 1.0)


def cmd_link_names(args: argparse.Namespace) -> None:
    """Resolve person-like `name` entities to `ipn` identities by name.

    For every person-like name in the DB, find the strongest matching `ipn`
    identity (a person who published РНОКПП). A conservative, unique match above
    ``--min-score`` becomes an ``identity`` edge with ``dataset='name_resolve'``.

    This is heuristic: use it to *suggest* cross-base identities (e.g. a wanted
    person who is also a debtor). It never invents identifiers and never reverses
    anonymization. Edges can be removed via
    ``DELETE FROM edges WHERE dataset='name_resolve'``.
    """
    store = Store(args.db)
    db = store.db
    # Gather person-like name entities (title or normalized value).
    name_rows = db.execute(
        "SELECT entity_id, COALESCE(NULLIF(title,''), value) display, value "
        "FROM entities WHERE type='name'").fetchall()
    ipn_rows = db.execute(
        "SELECT entity_id, COALESCE(NULLIF(title,''), '') display "
        "FROM entities WHERE type='ipn'").fetchall()

    # Index ipn display names -> entity id, skipping empties.
    ipn_candidates: list[tuple[int, list[str]]] = []
    for eid, disp in ipn_rows:
        toks = _name_tokens(disp)
        if len(toks) >= 2:
            ipn_candidates.append((eid, toks))

    if not ipn_candidates:
        print("Нет ipn-идентичностей (людей с РНОКПП) для разрешения имён.")
        return

    accepted = rejected_low = rejected_tie = not_person = 0
    rows_out = []
    # Idempotency: collect every endpoint already used in a name_resolve edge so a
    # repeated run skips already-resolved names instead of re-scoring them.
    already_endpoints = set()
    for (x, y) in db.execute(
            "SELECT a, b FROM edges WHERE kind=? AND dataset='name_resolve'",
            (IDENTITY_EDGE,)):
        already_endpoints.add(x)
        already_endpoints.add(y)
    for name_id, disp, nval in name_rows:
        if name_id in already_endpoints:
            continue
        name_tokens = _name_tokens(disp or nval)
        if not is_person_like_name(disp or nval):
            not_person += 1
            continue
        # score against each ipn
        best = None
        second = 0.0
        for ipn_id, ipn_tokens in ipn_candidates:
            s = score_person_name(name_tokens, ipn_tokens)
            if s is None:
                continue
            if best is None or s > best[0]:
                if best is not None:
                    second = best[0]
                best = (s, ipn_id)
            elif s > second:
                second = s
        if best is None:
            rejected_low += 1
            continue
        score, ipn_id = best
        if score < args.min_score:
            rejected_low += 1
            continue
        # Require a clear best (runner-up not within 0.2 of best) to avoid ties.
        if score - second < 0.2:
            rejected_tie += 1
            continue
        # add identity edge name->ipn
        a, b = sorted((name_id, ipn_id))
        db.execute(
            "INSERT INTO edges(a,b,kind,dataset,weight) VALUES(?,?,?,?,1) "
            "ON CONFLICT(a,b,kind,dataset) DO UPDATE SET weight=weight+1",
            (a, b, IDENTITY_EDGE, "name_resolve"))
        accepted += 1
        rows_out.append((disp, score))
    db.commit()
    print(f"name-resolution: принято {accepted:,}, пропущено(низк.) {rejected_low:,}, "
          f"пропущено(неоднозначно) {rejected_tie:,}, не-лица {not_person:,}")
    if args.limit and rows_out:
        print("примеры разрешений:")
        for disp, s in rows_out[: args.limit]:
            print(f"   {s:.3f}  {disp[:60]}")


# ---------------------------------------------------------------- co-org

def cmd_link_coorg(args: argparse.Namespace) -> None:
    """Add person-person edges for people who share the same company.

    Existing edges already relate each founder/signer/beneficial_owner to their
    company. This pass *closes the triangle*: two people who both relate to the
    same company (as founders, signers, or a mix) become connected by a
    ``co_org`` edge weighted by the number of shared companies. This surfaces
    real-world business/personal ties that are otherwise only reachable through
    the company node.

    Conservative guards:
      * only `name`-type people (natural persons) are linked;
      * only *small* co-groups are linked (``--max-group``), because very large
        shareholder lists (thousands of FOP-holders) produce noisy all-pairs
        cliques and mostly reflect shell/spam registrations;
      * idempotent: repeated runs only increment weights, never duplicate.
    """
    store = Store(args.db)

    # Edge endpoints are stored as (min, max), so either column may hold the
    # company id. Resolve each role-edge to its edrpou end by entity type.
    edrpou_ids = {eid for eid, in store.db.execute("SELECT entity_id FROM entities WHERE type='edrpou'")}
    comp_groups: dict[int, list[int]] = {}
    for a, b, in store.db.execute(
            "SELECT a, b FROM edges WHERE kind IN "
            "('founder','signer','beneficial_owner','linked','works_at')"):
        if a in edrpou_ids:
            comp = a; person = b
        elif b in edrpou_ids:
            comp = b; person = a
        else:
            continue
        if person == comp:
            continue
        comp_groups.setdefault(comp, []).append(person)

    people_type = dict(store.db.execute("SELECT entity_id, type FROM entities"))
    max_group = args.max_group
    edges_added = skipped_groups = total_people = 0
    for _comp, people in comp_groups.items():
        # keep only natural persons, dedup within the group
        uniq = list(dict.fromkeys(p for p in people if people_type.get(p) == "name"))
        if len(uniq) < 2:
            continue
        total_people += len(uniq)
        if len(uniq) > max_group:
            skipped_groups += 1  # skip over-large groups (noise)
            continue
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                store.edge(uniq[i], uniq[j], "co_org", args.dataset)
                edges_added += 1
    store.commit()
    print(
        f"co-org: связей людей через общую компанию: {edges_added:,} "
        f"(групп>max_group пропущено: {skipped_groups:,}, людей в малых группах: {total_people:,})"
    )


# ---------------------------------------------------------------- add-people

def _load_edrpou_from_db(store: Store) -> dict[str, int]:
    return {v: eid for eid, v in store.db.execute("SELECT entity_id, value FROM entities WHERE type='edrpou'")}


def cmd_add_people(args: argparse.Namespace) -> None:
    """Extend an existing graph DB with person registers (best-effort per file).

    Opens ``links.db`` produced by ``build`` and ingests the person-subject
    registers declared in ``config/person_register_map.json``. Each register is
    processed independently: an unparseable or changed file logs a warning and
    is skipped without failing the run, so a single broken mirror never blocks
    publishing the core (ЄДР/ПДВ/ЄДРСР) graph.
    """
    store = Store(args.db)
    _EDRPOU_CACHE.update(_load_edrpou_from_db(store))
    people_map = load_people_map(getattr(args, "people_map", None))

    def run(register_id: str, path: str, rows) -> dict:
        desc = people_map.get(register_id)
        if not desc or desc.get("subject") not in ("person", "mixed"):
            return {"skipped": True}
        counts = ingest_person_rows(store, register_id, desc, rows, _EDRPOU_CACHE)
        store.commit()
        return counts

    total = {"rows": 0, "people": 0, "identities": 0, "org_edges": 0, "failed": 0, "skipped": 0}
    specs = [("xml", s) for s in args.xml_register or []] + \
            [("csv", s) for s in args.csv_register or []] + \
            [("json", s) for s in args.json_register or []] + \
            [("xlsx", s) for s in args.xlsx_register or []] + \
            [("zipcsv", s) for s in args.zipcsv_register or []]
    if not specs:
        print("Нет реестров: укажите --xml-register/--csv-register/--json-register/--xlsx-register/--zipcsv-register (name=path).")
        return
    for fmt, spec in specs:
        register_id, _, path = spec.partition("=")
        desc = people_map.get(register_id) or {}
        if not desc or desc.get("subject") not in ("person", "mixed"):
            total["skipped"] += 1
            print(f"{register_id}: нет записи person-subject в person_register_map.json — пропуск")
            continue
        if desc.get("enabled") is False:
            total["skipped"] += 1
            print(f"{register_id}: помечен enabled=false в маппинге — пропуск")
            continue
        try:
            if fmt == "xml":
                rows = iter_xml_register(path, getattr(args, "encoding", "utf-8"))
            elif fmt == "csv":
                rows = iter_delimited(path)
            elif fmt == "json":
                rows = iter_json_register(path)
            elif fmt == "xlsx":
                rows = iter_xlsx_register(path, desc.get("sheet"))
            else:
                rows = iter_zip_csv(path)
            counts = run(register_id, path, rows)
            if counts.get("skipped"):
                continue
            print(f"{register_id}: {counts['rows']:,} строк, людей: {counts['people']:,}, "
                  f"РНОКПП: {counts['identities']:,}, связей с орг: {counts['org_edges']:,}")
            for k in ("rows", "people", "identities", "org_edges"):
                total[k] += counts[k]
        except Exception as exc:  # best-effort per-source isolation
            total["failed"] += 1
            print(f"{register_id} ({path}): пропущен — {type(exc).__name__}: {exc}")
    store.commit()
    print(f"add-people готово: людей {total['people']:,}, РНОКПП {total['identities']:,}, "
          f"связей с орг {total['org_edges']:,} | пропущено {total['skipped']}, ошибок {total['failed']} -> {args.db}")


# ---------------------------------------------------------------- inspect

def _sample_rows(filetype: str, path: str | Path, encoding: str | None, limit: int):
    filetype = filetype or Path(path).suffix.lower().lstrip(".")
    if filetype == "json":
        yield from list(iter_json_register(path))[:limit]
    elif filetype == "xml":
        for i, row in enumerate(iter_xml_register(path, encoding or "utf-8")):
            if i >= limit:
                break
            yield row
    elif filetype in ("csv", "txt"):
        for i, row in enumerate(iter_delimited(path, encoding or "cp1251")):
            if i >= limit:
                break
            yield row
    elif filetype in ("xlsx", "xls"):
        for i, row in enumerate(iter_xlsx_register(path)):
            if i >= limit:
                break
            yield row
    elif filetype == "zipcsv":
        for i, row in enumerate(iter_zip_csv(path)):
            if i >= limit:
                break
            yield row
    else:
        sys.exit(f"неизвестный формат: {filetype}")


def cmd_inspect(args: argparse.Namespace) -> None:
    """Print detected person/identity/org columns of a register sample.

    Used to *confirm* the field aliases in ``config/person_register_map.json``
    against a freshly downloaded register file before enabling it in a build.
    """
    rows = list(_sample_rows(args.type, args.path, args.encoding, args.rows))
    if not rows:
        print("Файл пуст или не распознан как набор записей.")
        return
    print(f"Образцов строк: {len(rows)} из {args.path}\n")
    for idx, row in enumerate(rows, 1):
        detected = canonical_fields(row)
        print(f"--- запись #{idx} ---")
        for key, value in row.items():
            print(f"   {key}: {value}")
        print("   распознано: " + ", ".join(f"{k}={v or '—'}" for k, v in detected.items()))


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

    print("\n-- Тождество (одно лицо под разными написаниями / РНОКПП) --")
    aliases = db.execute(
        "SELECT e.entity_id, e.type, e.value, e.title, x.kind, x.dataset "
        "FROM edges x JOIN entities e ON e.entity_id = "
        "  CASE WHEN x.a=? THEN x.b WHEN x.b=? THEN x.a END "
        "WHERE x.a=? OR x.b=? ORDER BY x.dataset",
        (eid, eid, eid, eid),
    ).fetchall()
    shown_identity = 0
    for row in aliases:
        if row["kind"] != IDENTITY_EDGE:
            continue
        shown_identity += 1
        title = row["title"] or row["value"]
        print(f"   {title[:60]}  ({row['type']}: {row['value']}) — как в базе {row['dataset']}")
    if shown_identity == 0:
        print("   (нет опубликованного РНОКПП-тождества в этом графе)")

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
    build.add_argument("--xlsx-register", action="append", help="name=path.xlsx (openpyxl)")
    build.add_argument("--zipcsv-register", action="append", help="name=path.zip (CSV внутри zip)")
    build.add_argument("--edrsr-parquet", action="append", help="glob паркет-частей ЄДРСР")
    build.add_argument("--encoding", default="utf-8", help="кодировка XML-реестров")
    build.add_argument("--people-map", help="файл person↔register маппинга (по умолчанию config/person_register_map.json)")
    build.set_defaults(func=cmd_build)

    addp = sub.add_parser("add-people", help="добавить person-реестры в существующий граф (best-effort)")
    addp.add_argument("--db", required=True)
    addp.add_argument("--xml-register", action="append", help="name=path.zip (RECORD-XML)")
    addp.add_argument("--csv-register", action="append", help="name=path.csv")
    addp.add_argument("--json-register", action="append", help="name=path.json")
    addp.add_argument("--xlsx-register", action="append", help="name=path.xlsx (openpyxl)")
    addp.add_argument("--zipcsv-register", action="append", help="name=path.zip (CSV внутри zip)")
    addp.add_argument("--encoding", default="utf-8", help="кодировка XML-реестров")
    addp.add_argument("--people-map", help="файл person↔register маппинга (по умолчанию config/person_register_map.json)")
    addp.set_defaults(func=cmd_add_people)

    lnk = sub.add_parser("link-names", help="разрешить name-сущности к ipn-идентичностям по ФИО (консервативно)")
    lnk.add_argument("--db", required=True)
    lnk.add_argument("--min-score", type=float, default=0.95, help="порог уверенности (0..1), по умолчанию 0.95")
    lnk.add_argument("--limit", type=int, default=10, help="сколько примеров вывести (0 = не выводить)")
    lnk.set_defaults(func=cmd_link_names)

    coorg = sub.add_parser("co-org", help="связать людей, делящих одну компанию (замкнуть founder/signer треугольники)")
    coorg.add_argument("--db", required=True)
    coorg.add_argument("--dataset", default="co_org", help="имя датасета для рёбер (по умолчанию co_org)")
    coorg.add_argument("--max-group", type=int, default=40, help="максимум людей в группе компании для связывания (защита от шумных гигантских групп)")
    coorg.set_defaults(func=cmd_link_coorg)

    inspect_ = sub.add_parser("inspect", help="распознать колонки персон/идентификаторов в файле реестра")
    inspect_.add_argument("path", help="CSV/JSON/ZIP-XML файл")
    inspect_.add_argument("--type", choices=["csv", "json", "xml", "xlsx", "zipcsv"], default=None, help="формат (иначе угадать по расширению)")
    inspect_.add_argument("--encoding", default=None, help="кодировка для CSV/XML (иначе utf-8/cp1251)")
    inspect_.add_argument("--rows", type=int, default=3, help="сколько строк показать")
    inspect_.set_defaults(func=cmd_inspect)

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
