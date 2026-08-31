"""Tests for the EDRSR full-text fetcher (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib.util

spec = importlib.util.spec_from_file_location("edrsr_texts", Path(__file__).resolve().parents[1] / "scripts" / "edrsr_texts.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_state_roundtrip(tmp_path):
    state = {"fetched": ["1", "2"], "failed": [{"doc_id": "3", "url": "x", "reason": "boom"}] * 6000}
    p = tmp_path / "state.json"
    m.save_state(p, state)
    loaded = m.load_state(p)
    assert loaded["fetched"] == ["1", "2"]
    assert len(loaded["failed"]) == 5000  # bounded


def test_document_text_html_and_rtf():
    html = "<html><body><p>Рішення суду</p><script>bad()</script></body></html>".encode()
    assert "Рішення суду" in m.document_text("https://x/a.html", html)
    assert "bad()" not in m.document_text("https://x/a.html", html)
    rtf = "{\\rtf1 Рiшення суду}".encode()
    assert "Рiшення суду" in m.document_text("https://x/a.rtf", rtf)
    assert m.document_text("https://x/a.pdf", b"%PDF") == ""


def test_iter_pending_filters_and_dedupes(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.Table.from_pylist([
        {"document_id": "1", "source_url": "https://x/1.rtf"},
        {"document_id": "1", "source_url": "https://x/1.rtf"},      # dupe
        {"document_id": "2", "source_url": None},                    # no url
        {"document_id": "3", "source_url": "https://x/3.php"},       # not a document
    ])
    part = tmp_path / "part.parquet"
    pq.write_table(table, part)
    seen = [doc for doc, _, _ in m.iter_pending([part], done=set())]
    assert seen == ["1"]
    assert [doc for doc, _, _ in m.iter_pending([part], done={"1"})] == []
