"""The CKAN API truncates responses sometimes; fetch() must retry transient errors."""
import http.client
import importlib.util
import io
import json
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "data_gov_ua_discovery", ROOT / "scripts" / "data_gov_ua_discovery.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_retries_transient_incomplete_read():
    payload = json.dumps({"result": {"count": 1, "results": [{"name": "x"}]}}).encode()
    calls = {"n": 0}

    def flaky(req, timeout=60):
        calls["n"] += 1
        if calls["n"] < 3:
            raise http.client.IncompleteRead(b"partial", 100)
        return _FakeResponse(payload)

    with mock.patch.object(m.urllib.request, "urlopen", flaky), \
         mock.patch.object(m.time, "sleep", lambda s: None):
        page = m.fetch("Україна")
    assert page["result"]["count"] == 1
    assert calls["n"] == 3


def test_fetch_gives_up_after_all_attempts():
    def always_broken(req, timeout=60):
        raise http.client.IncompleteRead(b"partial", 100)

    try:
        with mock.patch.object(m.urllib.request, "urlopen", always_broken), \
             mock.patch.object(m.time, "sleep", lambda s: None):
            m.fetch("Україна")
    except http.client.IncompleteRead:
        return
    raise AssertionError("fetch must raise after exhausting retry attempts")


def test_catalog_falls_back_when_api_unavailable(tmp_path):
    """Если CKAN отдаёт 429/502, каталог в репозитории остаётся рабочим, job не падает."""
    import sys as _sys
    from unittest import mock

    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"source": "data.gov.ua", "datasets": [{"id": "1"}, {"id": "2"}]}), encoding="utf-8")
    status = tmp_path / "catalog-status.json"

    def throttled(req, timeout=60):
        raise m.urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    argv = [
        "data_gov_ua_discovery.py",
        "--output",
        str(catalog),
        "--fallback-on-error",
        "--status-output",
        str(status),
    ]
    with mock.patch.object(m.urllib.request, "urlopen", throttled), \
         mock.patch.object(m.time, "sleep", lambda s: None), \
         mock.patch.object(_sys, "argv", argv):
        m.main()

    kept = json.loads(catalog.read_text(encoding="utf-8"))
    assert [d["id"] for d in kept["datasets"]] == ["1", "2"]
    saved = json.loads(status.read_text(encoding="utf-8"))
    assert saved["refreshed"] is False
    assert saved["datasets"] == 2


def test_catalog_still_fails_without_fallback(tmp_path):
    """Без флага безопасности отсутствие источника — по-прежнему ошибка пайплайна."""
    import sys as _sys
    from unittest import mock

    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"datasets": [{"id": "1"}]}), encoding="utf-8")
    argv = ["data_gov_ua_discovery.py", "--output", str(catalog), "--status-output", str(tmp_path / "s.json")]

    def throttled(req, timeout=60):
        raise m.urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)

    try:
        with mock.patch.object(m.urllib.request, "urlopen", throttled), \
             mock.patch.object(m.time, "sleep", lambda s: None), \
             mock.patch.object(_sys, "argv", argv):
            m.main()
    except m.urllib.error.HTTPError:
        return
    raise AssertionError("без --fallback-on-error недоступный API должен валить запуск")
