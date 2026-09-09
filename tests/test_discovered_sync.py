"""Tests for incremental discovered-data decisions."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync", ROOT / "scripts" / "data_gov_ua_discovered_sync.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_same_resource_prefers_source_hash():
    prior = {"url": "https://example.test/a.csv", "source_hash": "abc", "source_last_modified": "old", "source_size": 1}
    current = {"url": "https://example.test/a.csv", "hash": "abc", "last_modified": "new", "size": 2}
    assert m.same_resource(prior, current)


def test_same_resource_uses_metadata_when_hash_missing():
    prior = {"url": "https://example.test/a.csv", "source_last_modified": "2026-09-01", "source_size": 10}
    current = {"url": "https://example.test/a.csv", "hash": None, "last_modified": "2026-09-01", "size": 10}
    assert m.same_resource(prior, current)


def test_changed_resource_is_not_skipped():
    prior = {"url": "https://example.test/a.csv", "source_hash": "abc"}
    current = {"url": "https://example.test/a.csv", "hash": "def", "last_modified": None, "size": None}
    assert not m.same_resource(prior, current)
