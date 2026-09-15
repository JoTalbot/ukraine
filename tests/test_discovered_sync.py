"""Tests for incremental discovered-data decisions and retry behavior."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_retry_wait_honors_retry_after_and_is_bounded():
    response = type("Response", (), {"headers": {"Retry-After": "120"}})()
    assert m._retry_wait(response, 1) == m.MAX_RETRY_WAIT


def test_retry_wait_honors_http_date(monkeypatch):
    monkeypatch.setattr(m.time, "time", lambda: 1_000.0)
    response = SimpleNamespace(headers={"Retry-After": "Thu, 01 Jan 1970 00:16:50 GMT"})
    assert m._retry_wait(response, 1) == 10.0


def test_retry_wait_falls_back_to_exponential_backoff():
    response = type("Response", (), {"headers": {}})()
    assert m._retry_wait(response, 1) == 2
    assert m._retry_wait(response, 3) == 8


# --- v2: предпроверка хостов и классификация блокеров источника ---

def test_host_of_extracts_domain():
    assert m.host_of("https://opendata.gov.ua/dataset/x/resource/y/download/z.csv") == "opendata.gov.ua"
    assert m.host_of("") == ""


def test_probe_host_marks_timeout_as_unreachable(monkeypatch):
    monkeypatch.setattr(
        m.requests, "head",
        lambda *a, **k: (_ for _ in ()).throw(m.requests.exceptions.ReadTimeout("silent TLS")),
    )
    result = m.probe_host("opendata.gov.ua", timeout=0.1)
    assert result["reachable"] is False
    assert "ReadTimeout" in result["detail"]


def test_probe_host_marks_any_http_answer_as_reachable(monkeypatch):
    class Response:
        status_code = 403

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(m.socket, "create_connection", lambda *a, **k: FakeSocket())
    monkeypatch.setattr(m.requests, "head", lambda *a, **k: Response())
    result = m.probe_host("example.test", timeout=0.1)
    assert result["reachable"] is True
    assert result["detail"] == "http 403"


def test_classify_exception_separates_source_from_resource():
    assert m.classify_exception(m.requests.exceptions.ReadTimeout("x")) == m.SOURCE_UNAVAILABLE
    response = m.requests.Response()
    response.status_code = 429
    assert m.classify_exception(m.requests.HTTPError("429", response=response)) == m.SOURCE_THROTTLED
    assert m.classify_exception(RuntimeError("bad archive")) == m.RESOURCE_ERROR


def test_unreachable_host_blocks_without_download_attempt(monkeypatch, tmp_path):
    """Ресурсы мёртвого хоста помечаются blocked, скачивание не запускается."""
    calls = []

    def never(*a, **k):
        calls.append(a)
        raise AssertionError("download must not be attempted for a blocked host")

    monkeypatch.setattr(m, "download_with_retries", never)
    dataset = {
        "id": "ds-1",
        "name": "пример",
        "url": "https://data.gov.ua/dataset/ds-1",
        "resources": [
            {"url": "https://opendata.gov.ua/dataset/ds-1/resource/r1/download/a.csv", "format": "CSV"},
            {"url": "https://opendata.gov.ua/dataset/ds-1/resource/r2/download/b.csv", "format": "CSV"},
        ],
    }
    ctx = {
        "root": tmp_path,
        "hf": None,
        "repo": "test/repo",
        "args": SimpleNamespace(max_dataset_files=0, max_file_mb=0, incremental=False),
        "previous": {},
        "health": {"opendata.gov.ua": {"host": "opendata.gov.ua", "reachable": False, "latency_ms": 15000, "detail": "https: ReadTimeout"}},
    }
    entry = m.sync_dataset(dataset, ctx)
    assert calls == []
    assert entry["failed"] == []
    assert len(entry["blocked"]) == 2
    assert {b["kind"] for b in entry["blocked"]} == {m.SOURCE_UNAVAILABLE}
    assert "unreachable" in entry["blocked"][0]["reason"]


def test_source_health_reports_unreachable_hosts(tmp_path):
    health = {
        "opendata.gov.ua": {"host": "opendata.gov.ua", "reachable": False, "latency_ms": 15000, "detail": "https: ReadTimeout"},
        "data.gov.ua": {"host": "data.gov.ua", "reachable": True, "latency_ms": 900, "detail": "http 200"},
    }
    path = m.write_source_health(health, tmp_path / "source-health.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["unreachable_hosts"] == ["opendata.gov.ua"]
    assert payload["schema_version"] == 1
