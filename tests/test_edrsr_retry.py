"""Retry hardening for court-registry / data.gov.ua fetchers (EDRSR)."""
import http.client
import importlib.util
import io
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


sync = _load("edrsr_sync")
texts = _load("edrsr_texts")


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def headers(self):
        return {"ETag": "v1"}


def test_http_json_retries_transient_failures():
    calls = {"n": 0}

    def flaky(req, timeout=60):
        calls["n"] += 1
        if calls["n"] < 3:
            raise http.client.IncompleteRead(b"x", 10)
        return _FakeResponse(b'{"success": true}')

    with mock.patch.object(sync, "urlopen", flaky), \
         mock.patch.object(sync.time, "sleep", lambda s: None):
        assert sync.http_json("http://example") == {"success": True}
    assert calls["n"] == 3


def test_texts_fetch_gives_up_after_attempts():
    def broken(req, timeout=60):
        raise http.client.IncompleteRead(b"x", 10)

    try:
        with mock.patch.object(texts.urllib.request, "urlopen", broken), \
             mock.patch.object(texts.time, "sleep", lambda s: None):
            texts.fetch("http://example/doc.rtf")
    except http.client.IncompleteRead:
        return
    raise AssertionError("fetch must raise after exhausting retries")


def test_download_removes_partial_file_on_final_failure(tmp_path):
    def broken(req, timeout=300):
        raise http.client.IncompleteRead(b"x", 10)

    target = tmp_path / "archive.zip"
    try:
        with mock.patch.object(sync, "urlopen", broken), \
             mock.patch.object(sync.time, "sleep", lambda s: None):
            sync.download("http://example/edrsr.zip", target)
    except http.client.IncompleteRead:
        pass
    else:
        raise AssertionError("download must raise after exhausting retries")
    assert not target.exists(), "truncated archive must be removed on failure"
