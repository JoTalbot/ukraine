import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.entity_links import (
    Store,
    extract_edrpou_codes,
    looks_like_date,
    normalize_name,
    parse_person_role,
    resolve_entity,
)


def test_normalize_name():
    assert normalize_name("  Іваненко    Петро  Олексійович ") == "ІВАНЕНКО ПЕТРО ОЛЕКСІЙОВИЧ"
    assert normalize_name("ТОВʼХрест") == "ТОВ'ХРЕСТ"


def test_date_exclusion():
    assert looks_like_date("16102003") is True
    assert looks_like_date("35197641") is False  # plausible EDRPOU


def test_extract_edrpou_codes_whitelist():
    text = "позивач 35197641, відповідач 14359609, дата 16102003, справа 500/2026"
    codes = extract_edrpou_codes(text, whitelist={"35197641"})
    assert codes == ["35197641"]


def test_parse_person_role():
    assert parse_person_role("Ковальова І. В.; частка - 1000,00 грн") == ("Ковальова І. В.", "")
    assert parse_person_role("Петренко О. О. - директор")[0] == "Петренко О. О."


def test_store_edges_accumulate():
    store = Store(":memory:")
    a = store.entity("edrpou", "11111111", "Товариство")
    b = store.entity("edrpou", "22222222", "Концерн")
    store.edge(a, b, "co_litigant", "edrsr")
    store.edge(a, b, "co_litigant", "edrsr")
    weight = store.db.execute("SELECT weight FROM edges").fetchone()[0]
    assert weight == 2


def test_resolve_entity_by_prefix():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE entities (entity_id INTEGER PRIMARY KEY, type TEXT, value TEXT, title TEXT);
        INSERT INTO entities VALUES (1, 'edrpou', '35197641', 'ТОВ «Альфа»');
    """)
    row = resolve_entity(db, "351976413199", None)  # ПДВ-номер → префикс 8
    assert row is not None and row[2] == "35197641"
