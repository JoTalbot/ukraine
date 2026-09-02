"""The CKAN API truncates responses sometimes; fetch() must retry transient errors."""
import http.client
import io
import json
import importlib.util
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
