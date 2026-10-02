from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from backend.quant_pro import vendor_api


class _DummyResponse:
    def __init__(self, payload, *, content_type="application/json"):
        self._payload = payload
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_fetch_ohlcv_chunk_treats_no_data_as_empty(monkeypatch):
    monkeypatch.setattr(
        vendor_api.requests,
        "get",
        lambda *args, **kwargs: _DummyResponse({"s": "no_data", "nextTime": 1775107220}),
    )

    df = vendor_api.fetch_ohlcv_chunk("MANUFACTURING", 1704067200, 1775097600)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_fetch_ohlcv_chunk_normalizes_millisecond_timestamps(monkeypatch):
    seen = {}

    def fake_get(_url, *, params, **_kwargs):
        seen.update(params)
        return _DummyResponse({"s": "no_data"})

    monkeypatch.setattr(vendor_api.requests, "get", fake_get)

    vendor_api.fetch_ohlcv_chunk("NABIL", 1704067200000, 1775097600000)

    assert seen["rangeStartDate"] == 1704067200
    assert seen["rangeEndDate"] == 1775097600


def test_fetch_ohlcv_chunk_treats_html_error_page_as_empty(monkeypatch):
    monkeypatch.setattr(
        vendor_api.requests,
        "get",
        lambda *args, **kwargs: _DummyResponse("<html>error</html>", content_type="text/html; charset=utf-8"),
    )

    df = vendor_api.fetch_ohlcv_chunk("ACLBSL", 1704067200, 1775097600)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_fetch_ohlcv_chunk_does_not_retry_http_429(monkeypatch):
    calls = 0

    def rate_limited(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        error = vendor_api.requests.HTTPError("429 Too Many Requests")
        error.response = SimpleNamespace(status_code=429, headers={"Retry-After": "60"})
        raise error

    monkeypatch.setattr(vendor_api._rate_limiter, "wait", lambda: None)
    monkeypatch.setattr(vendor_api.requests, "get", rate_limited)

    with pytest.raises(vendor_api.requests.HTTPError, match="429"):
        vendor_api.fetch_ohlcv_chunk("AAA", 1704067200, 1775097600)
    assert calls == 1
