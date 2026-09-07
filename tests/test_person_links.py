import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.entity_links import (
    DEFAULT_PEOPLE_MAP,
    IDENTITY_EDGE,
    Store,
    canonical_fields,
    ingest_person_rows,
    load_people_map,
    normalize_name,
)


def test_people_map_file_present_and_well_formed():
    assert DEFAULT_PEOPLE_MAP.exists()
    registers = load_people_map(str(DEFAULT_PEOPLE_MAP))
    # A couple of person-subject bases must be declared.
    for reg_id in ("wanted_fugitives", "sanctions", "bank_ownership"):
        desc = registers.get(reg_id)
        assert desc and desc["subject"] in ("person", "mixed")
        assert desc.get("fields", {}).get("person")


def test_canonical_fields_person_and_ipn():
    out = canonical_fields({"ПІБ": "Іваненко Петро", "РНОКПП": "1111111111"})
    assert out["person"] == "Іваненко Петро"
    assert out["ipn"] == "1111111111"


def test_canonical_fields_edrpou_and_org():
    out = canonical_fields({"name": "ТОВ «Альфа»", "edrpou": "12345678"})
    assert out["edrpou"] == "12345678"
    assert "Альфа" in out["org"]


def test_same_rnokpp_unifies_person_across_registers():
    store = Store(":memory:")
    company = store.entity("edrpou", "12345678", "ТОВ «Альфа»")
    idx = {"12345678": company}

    wanted = {"subject": "person", "fields": {"person": ["ПІБ"], "ipn": ["РНОКПП"]}}
    debtors = {"subject": "person", "fields": {"person": ["ПІБ"], "ipn": ["ІПН"]}}
    ingest_person_rows(store, "wanted_fugitives", wanted,
                       [{"ПІБ": "Іваненко Петро Олексійович", "РНОКПП": "1111111111"}], idx)
    ingest_person_rows(store, "debtors", debtors,
                       [{"ПІБ": "Іваненко Петро Олексійович", "ІПН": "1111111111"}], idx)

    ipn_id = store.db.execute(
        "SELECT entity_id FROM entities WHERE type='ipn' AND value='1111111111'").fetchone()[0]
    bases = {r[0] for r in store.db.execute(
        "SELECT DISTINCT dataset FROM mentions WHERE entity_id=?", (ipn_id,))}
    assert bases == {"wanted_fugitives", "debtors"}

    # A name-entity alias is linked to the identity by an identity edge.
    n_identity = store.db.execute(
        "SELECT COUNT(*) FROM edges WHERE kind=?", (IDENTITY_EDGE,)).fetchone()[0]
    assert n_identity >= 1


def test_person_org_edge_by_edrpou():
    store = Store(":memory:")
    company = store.entity("edrpou", "12345678", "ТОВ «Альфа»")
    idx = {"12345678": company}
    desc = {"subject": "person", "org_edge": "works_at",
            "fields": {"person": ["ПІБ"], "ipn": ["ІПН"], "edrpou": ["ЄДРПОУ"]}}
    counts = ingest_person_rows(store, "court_experts", desc,
                                [{"ПІБ": "Сидоренко Олег", "ІПН": "3333333333", "ЄДРПОУ": "12345678"}], idx)
    assert counts["org_edges"] == 1
    row = store.db.execute("SELECT kind, dataset FROM edges WHERE kind='works_at'").fetchone()
    assert row == ("works_at", "court_experts")


def test_bad_ipn_is_ignored():
    store = Store(":memory:")
    desc = {"subject": "person", "fields": {"person": ["ПІБ"], "ipn": ["РНОКПП"]}}
    counts = ingest_person_rows(store, "wanted_fugitives", desc,
                                [{"ПІБ": "Ковальчук Ольга", "РНОКПП": "123" }], {})
    # no ipn entity created, only a name mention
    assert counts["identities"] == 0
    assert store.db.execute("SELECT COUNT(*) FROM entities WHERE type='ipn'").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM entities WHERE type='name'").fetchone()[0] == 1


def test_sentinel_name_skipped():
    store = Store(":memory:")
    desc = {"subject": "person", "fields": {"person": ["ПІБ"], "ipn": ["РНОКПП"]}}
    counts = ingest_person_rows(store, "wanted_fugitives", desc,
                                [{"ПІБ": "НЕВИЗНАЧЕНА ФІЗИЧНА ОСОБА", "РНОКПП": ""}], {})
    assert counts["rows"] == 1
    assert counts["people"] == 0
    assert store.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0


def test_normalize_name_uppercases():
    assert normalize_name("  Іваненко    Петро ") == "ІВАНЕНКО ПЕТРО"


def test_mixed_register_keeps_org_subjects():
    store = Store(":memory:")
    company = store.entity("edrpou", "12345678", "ПАТ «Завод»")
    idx = {"12345678": company}
    desc = {"subject": "mixed", "fields": {"person": ["ПІБ"], "edrpou": ["ЄДРПОУ"]}}
    counts = ingest_person_rows(store, "sanctions", desc,
                                [{"ЄДРПОУ": "12345678"}], idx)
    assert counts["org_subjects"] == 1
    assert counts["people"] == 0
    base = store.db.execute(
        "SELECT dataset FROM mentions WHERE entity_id=?", (company,)).fetchone()
    assert base == ("sanctions",)


def test_add_people_best_effort(tmp_path):
    """add-people ingests mapped person files and isolates a broken one."""
    import json as _json
    from argparse import Namespace

    from scripts.entity_links import cmd_add_people

    db = tmp_path / "links.db"
    good = tmp_path / "wanted.json"
    bad = tmp_path / "missing.json"
    bad.write_text("not json at all {", encoding="utf-8")
    _json.dump([{"ПІБ": "Іваненко Петро", "РНОККП": "", "РНОКПП": "1111111111"}], good.open("w"), ensure_ascii=False)

    args = Namespace(db=str(db), people_map=str(DEFAULT_PEOPLE_MAP), encoding="utf-8",
                     xml_register=None,
                     json_register=[f"wanted_fugitives={good}", f"missing_persons={bad}"],
                     csv_register=None, xlsx_register=None, zipcsv_register=None)
    cmd_add_people(args)

    store = Store(str(db))
    n_ipn = store.db.execute("SELECT COUNT(*) FROM entities WHERE type='ipn'").fetchone()[0]
    n_mentions = store.db.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
    # Good person file produced an identity; the broken file did not abort the run.
    assert n_ipn >= 1
    assert n_mentions >= 1
    # The broken source failed but add-people continued and committed.
    assert store.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] >= 3


def test_debtors_code_mode_splits_org_and_person():
    """A register with one name+id column splits person(10) from org(8) by code."""
    store = Store(":memory:")
    desc = {
        "subject": "mixed", "org_edge": "listed_in",
        "fields": {"name": ["DEBTOR_NAME"], "id": ["DEBTOR_CODE"]},
    }
    rows = [
        {"DEBTOR_NAME": "КОЛЕКТИВНЕ ПІДПРИЄМСТВО ОПТИКА №9", "DEBTOR_CODE": "20793942"},
        {"DEBTOR_NAME": "Іваненко Петро Олексійович", "DEBTOR_CODE": "1111111111"},
        {"DEBTOR_NAME": "Ковальчук Ольга", "DEBTOR_CODE": "2222222222"},
    ]
    ingest_person_rows(store, "debtors", desc, rows, {})
    types = {t: n for t, n in store.db.execute("SELECT type, COUNT(*) FROM entities GROUP BY type")}
    # two individuals -> two ipn, plus name entities; one legal -> one edrpou
    assert types["ipn"] == 2, types
    assert types["edrpou"] == 1, types
    # legal org must NOT become a person/name entity
    assert "name" not in types or types["name"] == 2, types
    # org subject recorded in mixed mode
    org_bases = store.db.execute(
        "SELECT COUNT(*) FROM mentions WHERE dataset='debtors'").fetchone()[0]
    assert org_bases >= 3


def test_iter_xlsx_register(tmp_path):
    from openpyxl import Workbook

    from scripts.entity_links import iter_xlsx_register
    p = tmp_path / "reg.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "ДСРУ"
    ws.append(["ПІБ", "РНОКПП", "РЕЄСТРАЦІЙНИЙ НОМЕР"])
    ws.append(["Іваненко Петро", "1111111111", "R-1"])
    wb.save(p)
    rows = list(iter_xlsx_register(p))
    assert rows == [{"ПІБ": "Іваненко Петро", "РНОКПП": "1111111111", "РЕЄСТРАЦІЙНИЙ НОМЕР": "R-1"}]


def test_iter_zip_csv(tmp_path):
    import zipfile

    from scripts.entity_links import iter_zip_csv
    z = tmp_path / "debt.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("29-ex_csv_erb.csv",
                    "DEBTOR_NAME;DEBTOR_CODE\nІваненко Петро;1111111111\nКОВАЛЬЧУК;2222222222\n")
    rows = list(iter_zip_csv(z))
    assert len(rows) == 2
    assert rows[0]["DEBTOR_CODE"] == "1111111111"
