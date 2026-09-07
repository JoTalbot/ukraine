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
    # A couple of person-subject bases must be declared (single-column or split-name).
    for reg_id in ("wanted_fugitives", "arbitration_managers", "debtors"):
        desc = registers.get(reg_id)
        assert desc and desc["subject"] in ("person", "mixed")
        fields = desc.get("fields", {})
        assert fields.get("person") or fields.get("person_parts") or (fields.get("name") and fields.get("id"))
    # Registers whose mirror is not row-ready must be disabled.
    for reg_id in ("sanctions", "bank_ownership", "declarations"):
        assert registers.get(reg_id, {}).get("enabled") is False


def test_person_parts_compose_full_name():
    store = Store(":memory:")
    desc = {"subject": "person", "fields": {
        "person_parts": [["LAST_NAME_U", "ПРІЗВИЩЕ"], ["FIRST_NAME_U", "ІМ'Я"], ["MIDDLE_NAME_U"]],
    }}
    counts = ingest_person_rows(store, "wanted_fugitives", desc,
                                [{"LAST_NAME_U": "ЗАХАРОВ", "FIRST_NAME_U": "В'ЯЧЕСЛАВ", "MIDDLE_NAME_U": "РОМАНОВИЧ"}], {})
    assert counts["people"] == 1
    row = store.db.execute("SELECT type, value, title FROM entities WHERE type='name'").fetchone()
    assert row[1] == "ЗАХАРОВ В'ЯЧЕСЛАВ РОМАНОВИЧ"
    # Russian/other variants of a missing part must not create a stray entity.
    assert store.db.execute("SELECT COUNT(*) FROM entities WHERE type='name'").fetchone()[0] == 1


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


def test_no_spurious_ipn_from_unrelated_10_digit_field():
    """Without an explicit ipn alias, a random 10-digit number must not become РНОКПП."""
    store = Store(":memory:")
    desc = {"subject": "person", "fields": {"person": ["FIO"]}}
    ingest_person_rows(store, "notaries", desc,
                       [{"FIO": "Воробей Тетяна Петрівна", "LICENSE": "761",
                         "REG_NUM": "0987654321"}], {})
    # LICENSE/REG_NUM are not identity codes -> no ipn entity, only a name person.
    assert store.db.execute("SELECT COUNT(*) FROM entities WHERE type='ipn'").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM entities WHERE type='name'").fetchone()[0] == 1


def test_person_org_edge_from_org_alias():
    store = Store(":memory:")
    desc = {"subject": "person", "org_edge": "works_at",
            "fields": {"person": ["FIO"], "org": ["NAME_OBJ"]}}
    ingest_person_rows(store, "notaries", desc,
                       [{"FIO": "Воробей Тетяна Петрівна",
                         "NAME_OBJ": "Іванківська державна нотаріальна контора"}], {})
    row = store.db.execute("SELECT kind, dataset, COUNT(*) FROM edges GROUP BY kind").fetchone()
    assert row and row[0] == "works_at" and row[1] == "notaries"


def test_name_tokens_and_person_like():
    from scripts.entity_links import _name_tokens, is_person_like_name
    assert _name_tokens("ЗАХАРОВ В'ЯЧЕСЛАВ РОМАНОВИЧ") == ["ЗАХАРОВ", "ВЯЧЕСЛАВ", "РОМАНОВИЧ"]
    assert is_person_like_name("Іваненко Петро Олексійович") is True
    assert is_person_like_name("ТОВ АЛЬФА") is False          # legal form
    assert is_person_like_name("Іванківська державна нотаріальна контора") is False
    assert is_person_like_name("Петренко О.") is True          # surname + initial
    # a 3-token non-patronymic tail should not be treated as a full person name
    assert is_person_like_name("СУД КИЇВСЬКИЙ АПЕЛЯЦІЙНИЙ") is False


def test_score_person_name_initials_and_full():
    from scripts.entity_links import score_person_name
    # exact full name -> high
    s = score_person_name(["ІВАНЕНКО", "ПЕТРО", "ОЛЕКСІЙОВИЧ"],
                          ["ІВАНЕНКО", "ПЕТРО", "ОЛЕКСІЙОВИЧ"])
    assert s is not None and s >= 0.9
    # surname exact, given as initial, same patronymic -> accepted
    s = score_person_name(["ІВАНЕНКО", "ПЕТРО", "ОЛЕКСІЙОВИЧ"],
                          ["ІВАНЕНКО", "П", "ОЛЕКСІЙОВИЧ"])
    assert s is not None and s >= 0.9
    # different surname -> not a candidate
    assert score_person_name(["ПЕТРЕНКО", "ПЕТРО", "ОЛЕКСІЙОВИЧ"],
                             ["ІВАНЕНКО", "ПЕТРО", "ОЛЕКСІЙОВИЧ"]) is None
    # same names but different patronymic -> rejected (different person)
    assert score_person_name(["ІВАНЕНКО", "ПЕТРО", "МИКОЛАЙОВИЧ"],
                             ["ІВАНЕНКО", "ПЕТРО", "ОЛЕКСІЙОВИЧ"]) is None


def _make_link_db(path):
    store = Store(path)
    # two ipn identities (debtors/ФОП published РНОКПП)
    store.entity("ipn", "1111111111", "Іваненко Петро Олексійович")
    store.entity("ipn", "2222222222", "Ковальчук Ольга Іванівна")
    # name-only person records
    store.entity("name", "ІВАНЕНКО ПЕТРО ОЛЕКСІЙОВИЧ", "Іваненко Петро Олексійович")
    store.entity("name", "ІВАНЕНКО ПЕТРО", "Іваненко Петро")       # partial (no patronymic)
    store.entity("name", "ТОВ АЛЬФА", "ТОВ АЛЬФА")                # org, must be ignored
    store.commit()
    return store


def test_cmd_link_names_resolves_unique(tmp_path):
    from argparse import Namespace

    from scripts.entity_links import cmd_link_names
    db = tmp_path / "links.db"
    _make_link_db(str(db))
    args = Namespace(db=str(db), min_score=0.9, limit=0)
    cmd_link_names(args)
    store = Store(str(db))
    rows = store.db.execute(
        "SELECT a, b, dataset FROM edges WHERE kind=? AND dataset='name_resolve'",
        (IDENTITY_EDGE,)).fetchall()
    # The full and the partial "Іваненко Петро" both resolve to the same ipn.
    assert len(rows) == 2, rows
    ipn_id = store.db.execute(
        "SELECT entity_id FROM entities WHERE type='ipn' AND value='1111111111'").fetchone()[0]
    name_ids = [r for r in store.db.execute(
        "SELECT DISTINCT CASE WHEN a=? THEN b ELSE a END FROM edges "
        "WHERE dataset='name_resolve' AND (a=? OR b=?)", (ipn_id, ipn_id, ipn_id))]
    # endpoints excluding ipn = 2 name entities
    assert len(name_ids) == 2


def test_cmd_link_names_ignores_orgs_and_is_idempotent(tmp_path):
    from argparse import Namespace

    from scripts.entity_links import cmd_link_names
    db = tmp_path / "links.db"
    _make_link_db(str(db))
    args = Namespace(db=str(db), min_score=0.9, limit=0)
    cmd_link_names(args)
    cmd_link_names(args)  # second run must not duplicate
    store = Store(str(db))
    n = store.db.execute(
        "SELECT COUNT(*) FROM edges WHERE dataset='name_resolve'").fetchone()[0]
    assert n == 2, n
