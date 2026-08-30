"""Lightweight quality gates for normalized EDRSR records."""
from __future__ import annotations

from collections.abc import Iterable

REQUIRED_KEYS = ("schema_version", "document_id", "text_sha256")


def validate_record(record: dict) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_KEYS:
        if key not in record:
            errors.append(f"missing:{key}")
    if record.get("text") and len(record["text"]) < 20:
        errors.append("text_too_short")
    return errors


def validate_records(records: Iterable[dict]) -> dict[str, int]:
    total = valid = invalid = 0
    for record in records:
        total += 1
        if validate_record(record):
            invalid += 1
        else:
            valid += 1
    return {"total": total, "valid": valid, "invalid": invalid}


def require_clean(stats: dict[str, int], max_invalid_ratio: float = 0.01) -> None:
    total = stats["total"]
    ratio = stats["invalid"] / total if total else 0.0
    if ratio > max_invalid_ratio:
        raise ValueError(f"quality gate failed: invalid_ratio={ratio:.4%} > {max_invalid_ratio:.2%}")
