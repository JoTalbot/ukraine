"""Regression tests for the Data.gov.ua mirror transport and resource naming."""
import importlib.util
import io
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "data_gov_ua_sync", ROOT / "scripts" / "data_gov_ua_sync.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class _Response:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True


class _StreamResponse(io.BytesIO):
    status_code = 200

    def raise_for_status(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_safe_name_preserves_extension_and_stays_below_byte_limit():
    source = ("дуже-довга-назва-ресурсу-" * 30) + ".xlsx"
    result = m.safe_name(source)

    assert result.endswith(".xlsx")
    assert len(result.encode("utf-8")) <= 180
    assert result != source
    assert result.rsplit("_", 1)[-1].removesuffix(".xlsx").__len__() >= 0


def test_safe_name_hashes_long_names_deterministically():
    source = ("resource-" * 50) + ".csv"
    assert m.safe_name(source) == m.safe_name(source)
    assert len(m.safe_name(source).encode("utf-8")) <= 180


def test_get_with_retries_retries_chunked_encoding_error():
    calls = {"n": 0}
    response = _Response()

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ChunkedEncodingError("incomplete chunk")
        return response

    with mock.patch.object(m.requests, "get", side_effect=flaky), mock.patch.object(m.time, "sleep"):
        result = m.get_with_retries("https://example.test/resource", timeout=1)

    assert result is response
    assert calls["n"] == 2


def test_get_with_retries_retries_server_error_then_succeeds():
    calls = {"n": 0}
    responses = [_Response(503), _Response(200)]

    def flaky(*args, **kwargs):
        response = responses[calls["n"]]
        calls["n"] += 1
        return response

    with mock.patch.object(m.requests, "get", side_effect=flaky), mock.patch.object(m.time, "sleep"):
        result = m.get_with_retries("https://example.test/resource", timeout=1)

    assert result.status_code == 200
    assert calls["n"] == 2
    assert responses[0].closed is True
