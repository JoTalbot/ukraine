"""Regression tests for the EDRSR export parser (delimiter + dictionaries)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.edrsr_sync import iter_records, normalize, sniff_delimiter


def _make_export(tmp_path: Path) -> Path:
    root = tmp_path / "extracted"
    root.mkdir()
    (root / "courts.csv").write_text(
        "court_code\tcourt_name\n500\tШостий апеляційний суд\n761\tЛьвівський окружовий адмінсуд\n",
        encoding="utf-8",
    )
    (root / "cause_categories.csv").write_text(
        'category_code\tname\n2036\t"Захоплення заручників"\n2210\t"Крадіжка"\n',
        encoding="utf-8",
    )
    (root / "documents.csv").write_text(
        "doc_id\tcourt_code\tjudgment_code\tjustice_kind\tcategory_code\tcause_num\tadjudication_date\t"
        "receipt_date\tjudge\tdoc_url\tstatus\tdate_publ\n"
        "1330\t761\t2\t1\t2210\t826/2789/24\t30.10.2024\t05.11.2024\tКовальчук О. В.\t"
        "https://reyestr.court.gov.ua/Review/11849529\tЗага�ьний\t01.11.2024\n"
        "1331\t500\t1\t2\t2036\t500/1540/26\t12.02.2026\t13.02.2026\tШевченко І. М.\t"
        "https://reyestr.court.gov.ua/Review/11849530\tЗага�ьний\t14.02.2026\n",
        encoding="utf-8",
    )
    return root


def test_sniff_delimiter():
    assert sniff_delimiter("a\tb\tc") == "\t"
    assert sniff_delimiter("a,b;c") == ","


def test_documents_are_parsed_and_enriched(tmp_path):
    root = _make_export(tmp_path)
    records = {rel: raw for raw, rel in iter_records(root)}
    # dictionary files must not leak as records
    assert set(records) == {"documents.csv"}
    rows = [raw for raw, rel in iter_records(root)]
    first = normalize(rows[0], "documents.csv", "deadbeef", "dataset-id")
    assert first["case_number"] == "826/2789/24"
    assert first["document_id"] == "1330"
    assert first["court"] == "Львівський окружовий адмінсуд"  # joined from courts.csv
    assert first["category"] == "Крадіжка"  # joined from cause_categories.csv
    assert first["judge"] == "Ковальчук О. В."
    assert first["decision_date"] == "30.10.2024"
    assert first["publication_date"] == "01.11.2024"
    assert first["source_url"].startswith("https://reyestr.court.gov.ua/")
    assert first["document_type"] == "2"
