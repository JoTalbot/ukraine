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


# ---- co-org: person-person edges through a shared company ----

def _build_coorg_db():
    """Company with 2 founders + 1 signer; another company sharing one founder."""
    store = Store(":memory:")
    comp_a = store.entity("edrpou", "11111111", "ТОВ «Альфа»")
    comp_b = store.entity("edrpou", "22222222", "ТОВ «Бета»")
    p1 = store.entity("name", "ІВАНЕНКО ПЕТРО ОЛЕКСІЙОВИЧ", "Іваненко Петро Олексійович")
    p2 = store.entity("name", "ПЕТРЕНКО ОЛЕНА ВАСИЛІВНА", "Петренко Олена Василівна")
    p3 = store.entity("name", "СИДОРЕНКО МАРІЯ ІВАНІВНА", "Сидоренко Марія Іванівна")
    store.edge(p1, comp_a, "founder", "edr")
    store.edge(p2, comp_a, "founder", "edr")
    store.edge(p3, comp_a, "signer", "edr")   # same company, mixed role
    store.edge(p1, comp_b, "founder", "edr")  # p1 shares B too -> extra weight
    store.commit()
    return store


def test_coorg_links_people_sharing_company(tmp_path):
    from types import SimpleNamespace as NS

    import scripts.entity_links as el
    db = str(tmp_path / "links.db")
    store2 = Store(db)
    ca = store2.entity("edrpou", "11111111", "Альфа")
    cb = store2.entity("edrpou", "22222222", "Бета")
    x = store2.entity("name", "ІВАНЕНКО ПЕТРО", "Іваненко Петро")
    y = store2.entity("name", "ПЕТРЕНКО ОЛЕНА", "Петренко Олена")
    z = store2.entity("name", "СИДОРЕНКО МАРІЯ", "Сидоренко Марія")
    store2.edge(x, ca, "founder", "edr")
    store2.edge(y, ca, "founder", "edr")
    store2.edge(z, ca, "signer", "edr")
    store2.edge(x, cb, "founder", "edr")
    store2.commit()
    el.cmd_link_coorg(NS(db=db, dataset="co_org", max_group=40))
    rows = store2.db.execute("SELECT a,b,kind,weight FROM edges WHERE kind='co_org'").fetchall()
    # 3 people in group A -> 3 pairs; x also in B alone (no partner) -> stays 3.
    assert len(rows) == 3, rows
    # weight of x-y should be 1 (only company A shared)
    for a, b, k, w in rows:
        assert w == 1
        assert k == "co_org"


def test_coorg_skips_oversized_group(tmp_path):
    from types import SimpleNamespace as NS

    import scripts.entity_links as el
    db = str(tmp_path / "links.db")
    store = Store(db)
    comp = store.entity("edrpou", "99999999", "МегаТОВ")
    for i in range(10):
        nm = f"ОСОБА {i:02d} ІВАНІВНА"
        person = store.entity("name", nm, nm)
        store.edge(person, comp, "founder", "edr")
    store.commit()
    el.cmd_link_coorg(NS(db=db, dataset="co_org", max_group=5))  # group(10) > 5 -> skip
    n = store.db.execute("SELECT COUNT(*) FROM edges WHERE kind='co_org'").fetchone()[0]
    assert n == 0


# ---- link-context: cross-register name↔name with a shared company as context ----

def _build_context_db(tmp_path):
    """One company; a full founder name in EDR + the same person as initials in
    another register, both attached to the company -> a context_resolve edge."""
    store = Store(_db := str(tmp_path / "ctx.db"))
    comp = store.entity("edrpou", "35197641", "ТОВ «Альфа»")
    # full name, seen in the company register
    full = store.entity("name", "ІВАНЕНКО ПЕТРО ОЛЕКСІЙОВИЧ", "Іваненко Петро Олексійович")
    store.edge(full, comp, "founder", "edr")
    store.mention(full, "edr", "rec1", "Іваненко Петро Олексійович")
    # same person, abbreviated, seen in a different register (works_at the company)
    init = store.entity("name", "ІВАНЕНКО П. О.", "Іваненко П. О.")
    store.edge(init, comp, "works_at", "other_register")
    store.mention(init, "other_register", "rec2", "Іваненко П. О.")
    store.commit()
    return store, _db, comp, full, init


def test_link_context_links_full_to_initials_cross_register(tmp_path):
    store, db, _comp, full, init = _build_context_db(tmp_path)
    from types import SimpleNamespace as NS

    import scripts.entity_links as el
    el.cmd_link_context(NS(db=db, dataset="context_resolve", max_group=40, min_score=0.95))
    rows = store.db.execute(
        "SELECT a,b,kind,dataset,weight FROM edges WHERE dataset='context_resolve'").fetchall()
    # exactly one identity edge between the two people, on the shared company
    assert len(rows) == 1, rows
    a, b, kind, _ds, w = rows[0]
    assert kind == "identity"
    assert {a, b} == {full, init}
    assert w == 1
    # the two original role edges are untouched
    assert store.db.execute(
        "SELECT COUNT(*) FROM edges WHERE kind NOT IN ('identity')").fetchone()[0] == 2


def test_link_context_skips_same_single_register(tmp_path):
    # both names only ever mentioned in the SAME one register -> not cross-register
    store = Store(_db := str(tmp_path / "ctx.db"))
    comp = store.entity("edrpou", "35197641", "Альфа")
    full = store.entity("name", "ІВАНЕНКО ПЕТРО ОЛЕКСІЙОВИЧ", None)
    init = store.entity("name", "ІВАНЕНКО П. О.", None)
    store.edge(full, comp, "founder", "edr")
    store.edge(init, comp, "signer", "edr")
    for e in (full, init):
        store.mention(e, "edr", "r", None)  # only edr
    store.commit()
    from types import SimpleNamespace as NS

    import scripts.entity_links as el
    el.cmd_link_context(NS(db=_db, dataset="context_resolve", max_group=40, min_score=0.95))
    assert store.db.execute(
        "SELECT COUNT(*) FROM edges WHERE dataset='context_resolve'").fetchone()[0] == 0


def test_link_context_requires_full_anchor(tmp_path):
    # two *abbreviated* names only -> no full anchor -> nothing linked
    store = Store(_db := str(tmp_path / "ctx.db"))
    comp = store.entity("edrpou", "35197641", "Альфа")
    a1 = store.entity("name", "ІВАНЕНКО П. О.", None)
    a2 = store.entity("name", "ІВАНЕНКО П. П.", None)
    store.edge(a1, comp, "founder", "edr")
    store.edge(a2, comp, "signer", "reg2")
    store.mention(a1, "edr", "r", None)
    store.mention(a2, "reg2", "r", None)
    store.commit()
    from types import SimpleNamespace as NS

    import scripts.entity_links as el
    el.cmd_link_context(NS(db=_db, dataset="context_resolve", max_group=40, min_score=0.95))
    assert store.db.execute(
        "SELECT COUNT(*) FROM edges WHERE dataset='context_resolve'").fetchone()[0] == 0


def test_link_context_skips_name_incompatible(tmp_path):
    # same shared company + different registers, but different surname -> no edge
    store = Store(_db := str(tmp_path / "ctx.db"))
    comp = store.entity("edrpou", "35197641", "Альфа")
    full = store.entity("name", "ІВАНЕНКО ПЕТРО ОЛЕКСІЙОВИЧ", None)
    other = store.entity("name", "ПЕТРЕНКО ПЕТРО ОЛЕКСІЙОВИЧ", None)  # founder too
    store.edge(full, comp, "founder", "edr")
    store.edge(other, comp, "founder", "reg2")
    store.mention(full, "edr", "r", None)
    store.mention(other, "reg2", "r", None)
    store.commit()
    from types import SimpleNamespace as NS

    import scripts.entity_links as el
    el.cmd_link_context(NS(db=_db, dataset="context_resolve", max_group=40, min_score=0.95))
    assert store.db.execute(
        "SELECT COUNT(*) FROM edges WHERE dataset='context_resolve'").fetchone()[0] == 0


def test_link_context_skips_oversized_group(tmp_path):
    store = Store(_db := str(tmp_path / "ctx.db"))
    comp = store.entity("edrpou", "35197641", "Альфа")
    # a genuine full↔initials pair that WOULD link on its own...
    full = store.entity("name", "ІВАНЕНКО ПЕТРО ОЛЕКСІЙОВИЧ", None)
    init = store.entity("name", "ІВАНЕНКО П. О.", None)
    store.edge(full, comp, "founder", "edr")
    store.edge(init, comp, "signer", "reg2")
    store.mention(full, "edr", "r", None)
    store.mention(init, "reg2", "r", None)
    # ...plus enough unrelated co-holders to push the group over max_group
    for i in range(7):
        cand = store.entity("name", f"ІВАНОВ І. {chr(65 + i)}", None)
        store.edge(cand, comp, "founder", f"reg{i + 10}")
        store.mention(cand, f"reg{i + 10}", "r", None)
    store.commit()
    from types import SimpleNamespace as NS

    import scripts.entity_links as el
    # 9 people in the company > max_group 5 -> whole company skipped (no links)
    el.cmd_link_context(NS(db=_db, dataset="context_resolve", max_group=5, min_score=0.95))
    assert store.db.execute(
        "SELECT COUNT(*) FROM edges WHERE dataset='context_resolve'").fetchone()[0] == 0
