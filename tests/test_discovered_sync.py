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


def test_throttled_host_is_not_hammered_with_retries(monkeypatch, tmp_path):
    """429 от источника: после порога остальные ресурсы хоста блокируются без скачивания."""
    calls = []

    def always_429(url, dest):
        calls.append(url)
        raise m.urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(m, "download_with_retries", always_429)
    resources = [
        {"url": f"https://data.gov.ua/dataset/ds-2/resource/r{i}/download/f{i}.csv", "format": "CSV"}
        for i in range(4)
    ]
    dataset = {"id": "ds-2", "name": "троттлинг", "url": "https://data.gov.ua/dataset/ds-2", "resources": resources}
    health = {"data.gov.ua": {"host": "data.gov.ua", "reachable": True, "latency_ms": 500, "detail": "http 200"}}
    ctx = {
        "root": tmp_path,
        "hf": None,
        "repo": "test/repo",
        "args": SimpleNamespace(max_dataset_files=0, max_file_mb=0, incremental=False),
        "previous": {},
        "health": health,
        "throttle_halt_after": 2,
    }
    entry = m.sync_dataset(dataset, ctx)
    assert len(calls) == 2, "после порога источник перестаём дёргать"
    assert entry["failed"] == []
    assert len(entry["blocked"]) == 4
    assert {b["kind"] for b in entry["blocked"]} == {m.SOURCE_THROTTLED}
    assert health["data.gov.ua"]["throttled"] is True
    assert health["data.gov.ua"]["throttle_hits"] == 2


def test_throttle_halt_can_be_disabled(monkeypatch, tmp_path):
    """При --throttle-halt-after 0 поведение прежнее: каждый ресурс пробуется сам."""
    calls = []

    def always_429(url, dest):
        calls.append(url)
        raise m.urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(m, "download_with_retries", always_429)
    dataset = {
        "id": "ds-3",
        "name": "без ограничений",
        "url": "https://data.gov.ua/dataset/ds-3",
        "resources": [
            {"url": f"https://data.gov.ua/dataset/ds-3/resource/r{i}/download/f{i}.csv", "format": "CSV"}
            for i in range(3)
        ],
    }
    ctx = {
        "root": tmp_path,
        "hf": None,
        "repo": "test/repo",
        "args": SimpleNamespace(max_dataset_files=0, max_file_mb=0, incremental=False),
        "previous": {},
        "health": {"data.gov.ua": {"host": "data.gov.ua", "reachable": True}},
        "throttle_halt_after": 0,
    }
    entry = m.sync_dataset(dataset, ctx)
    assert len(calls) == 3
    assert len(entry["blocked"]) == 3


def test_probe_host_flags_rate_limited_source(monkeypatch):
    """Хост отвечает 429 — он жив, но качать из него в этом прогоне нельзя."""
    class _Resp:
        status_code = 429

    class _Sock:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(m.socket, "create_connection", lambda *a, **k: _Sock())
    monkeypatch.setattr(m.requests, "head", lambda *a, **k: _Resp())
    result = m.probe_host("data.gov.ua", timeout=1)
    assert result["reachable"] is True
    assert result["throttled"] is True
    assert "rate limited" in result["detail"]


def test_rate_limited_host_blocks_resources_without_download(monkeypatch, tmp_path):
    """Если предпроверка увидела троттлинг, ресурсы хоста сразу идут в blocked."""
    def never(*a, **k):
        raise AssertionError("download must not be attempted on a throttled host")

    monkeypatch.setattr(m, "download_with_retries", never)
    dataset = {
        "id": "ds-4",
        "name": "rate limited",
        "url": "https://data.gov.ua/dataset/ds-4",
        "resources": [{"url": "https://data.gov.ua/dataset/ds-4/resource/r1/download/a.csv", "format": "CSV"}],
    }
    ctx = {
        "root": tmp_path,
        "hf": None,
        "repo": "test/repo",
        "args": SimpleNamespace(max_dataset_files=0, max_file_mb=0, incremental=False),
        "previous": {},
        "health": {"data.gov.ua": {"host": "data.gov.ua", "reachable": True, "throttled": True, "detail": "http 429 (rate limited)"}},
        "throttle_halt_after": 2,
    }
    entry = m.sync_dataset(dataset, ctx)
    assert entry["failed"] == []
    assert len(entry["blocked"]) == 1
    assert entry["blocked"][0]["kind"] == m.SOURCE_THROTTLED
