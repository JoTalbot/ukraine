from scripts.edrsr.normalize import normalize_record
from scripts.edrsr.validate import require_clean, validate_record, validate_records


def test_normalize_record_preserves_core_fields():
    record = normalize_record({"id": "42", "court_name": "Test court", "body": "A" * 30})
    assert record["document_id"] == "42"
    assert record["court"] == "Test court"
    assert len(record["text_sha256"]) == 64
    assert validate_record(record) == []


def test_unknown_fields_are_preserved():
    record = normalize_record({"id": "1", "body": "A" * 30, "future_field": "keep"})
    assert record["extra"]["future_field"] == "keep"


def test_quality_gate():
    stats = validate_records([normalize_record({"id": "1", "body": "A" * 30})])
    assert stats == {"total": 1, "valid": 1, "invalid": 0}
    require_clean(stats)
