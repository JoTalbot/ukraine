"""Normalize raw EDRSR exports into a stable record shape.

The official export format may evolve. This module deliberately accepts
common XML/JSON-like dictionaries and preserves unknown fields under `extra`
so ingestion does not silently discard information.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

SCHEMA_VERSION = "1.0"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_record(raw: dict[str, Any], source_file: str | None = None) -> dict[str, Any]:
    """Map an export record to the canonical EDRSR dataset schema."""
    aliases = {
        "case_number": ("case_number", "caseNo", "nomer_spravy", "caseNum"),
        "document_id": ("document_id", "id", "doc_id", "id_doc"),
        "court": ("court", "court_name", "sud"),
        "decision_date": ("decision_date", "date", "date_decision", "data"),
        "decision_type": ("decision_type", "type", "document_type"),
        "instance": ("instance", "court_instance", "instanciya"),
        "category": ("category", "category_name", "kategoriya"),
        "title": ("title", "name", "zagolovok"),
        "text": ("text", "body", "content", "document_text", "tekst"),
        "source_url": ("source_url", "url", "reyestr_url"),
    }

    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    used: set[str] = set()
    for canonical, candidates in aliases.items():
        for key in candidates:
            if key in raw:
                result[canonical] = _text(raw[key])
                used.add(key)
                break
        else:
            result[canonical] = None

    text = result.get("text") or ""
    result["text_sha256"] = sha256(text.encode("utf-8")).hexdigest() if text else None
    result["source_file"] = source_file
    result["ingested_at"] = datetime.now(timezone.utc).isoformat()
    result["extra"] = {str(k): v for k, v in raw.items() if k not in used}
    return result


def normalize_records(records: list[dict[str, Any]], source_file: str | None = None) -> list[dict[str, Any]]:
    return [normalize_record(record, source_file) for record in records]
