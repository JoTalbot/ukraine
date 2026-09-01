"""Tests for the EDRSR full-text fetcher (no network)."""
import sys
from io import BytesIO
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
    assert len(loaded["failed"]) == 5000


def test_document_text_html_and_rtf():
    html = "<html><body><p>Рішення суду</p><script>bad()</script></body></html>".encode()
    assert "Рішення суду" in m.document_text("https://x/a.html", html)
    assert "bad()" not in m.document_text("https://x/a.html", html)
    rtf = "{\\rtf1 Рiшення суду}".encode()
    assert "Рiшення суду" in m.document_text("https://x/a.rtf", rtf)


def test_document_text_pdf_and_docx():
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = BytesIO()
    writer.write(pdf)
    assert m.document_text("https://x/a.pdf", pdf.getvalue()) == ""

    from docx import Document
    document = Document()
    document.add_paragraph("Рішення суду")
    docx = BytesIO()
    document.save(docx)
    assert "Рішення суду" in m.document_text("https://x/a.docx", docx.getvalue())


def test_document_text_legacy_doc_requires_converter():
    import pytest
    with pytest.raises(ValueError, match="external text converter"):
        m.document_text("https://x/a.doc", b"binary")


def test_iter_pending_filters_and_dedupes(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.Table.from_pylist([
        {"document_id": "1", "source_url": "https://x/1.rtf"},
        {"document_id": "1", "source_url": "https://x/1.rtf"},
        {"document_id": "2", "source_url": None},
        {"document_id": "3", "source_url": "https://x/3.php"},
        {"document_id": "4", "source_url": "https://x/4.pdf?download=1"},
    ])
    part = tmp_path / "part.parquet"
    pq.write_table(table, part)
    seen = [doc for doc, _, _ in m.iter_pending([part], done=set())]
    assert seen == ["1", "4"]
    assert [doc for doc, _, _ in m.iter_pending([part], done={"1"})] == ["4"]
