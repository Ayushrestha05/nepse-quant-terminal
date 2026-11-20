"""Unit tests for HTTPS-only ProxyPool, Merolagani news-detail parser, and new strategy signals."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from backend.backtesting.nepse_event_signals import (
    generate_informed_trading_signals_at_date,
    generate_ipo_momentum_signals_at_date,
)
from backend.quant_pro.data_scrapers.proxy_pool import ProxyPool, ProxyPoolError
from backend.quant_pro.data_scrapers.sentiment_ingestion import (
    _fetch_url,
    parse_merolagani_news_detail,
)


def test_proxy_pool_never_falls_back_to_direct_in_proxy_only_mode(monkeypatch):
    called_direct = False

    def boom(*args, **kwargs):
        nonlocal called_direct
        called_direct = True
        raise AssertionError("Direct request must never be called in proxy_only mode")

    monkeypatch.setattr("requests.request", boom)
    monkeypatch.delenv("NQT_PROXIES", raising=False)

    pool = ProxyPool(proxies=[], proxy_only=True, auto_fetch=False, use_cache=False)
    with pytest.raises(ProxyPoolError):
        pool.get("https://merolagani.com/NewsDetail.aspx?newsID=60000")

    assert not called_direct


def test_proxy_pool_rejects_non_https_target():
    pool = ProxyPool(
        proxies=["http://127.0.0.1:8080"],
        proxy_only=True,
        auto_fetch=False,
        skip_health_check=True,
        use_cache=False,
    )
    with pytest.raises(ProxyPoolError, match="non-HTTPS"):
        pool.get("http://merolagani.com/Floorsheet.aspx")


def test_fetch_url_proxy_only_never_calls_direct_urllib(monkeypatch):
    def fail_direct(*_args, **_kwargs):
        raise AssertionError("Direct urllib must not run when proxy_only=True")

    monkeypatch.setattr(
        "backend.quant_pro.data_scrapers.sentiment_ingestion._fetch_via_urllib",
        fail_direct,
    )
    monkeypatch.setattr(
        "backend.quant_pro.data_scrapers.proxy_pool.get_proxy_pool",
        lambda **_kw: ProxyPool(proxies=[], proxy_only=True, auto_fetch=False, use_cache=False),
    )

    with pytest.raises(ProxyPoolError):
        _fetch_url("https://merolagani.com/NewsDetail.aspx?newsID=60000", proxy_only=True)


def test_parse_merolagani_news_detail_valid_and_malformed():
    html_full = """
    <html><body>
      <span id="ctl00_ContentPlaceHolder1_newsTitle">नबिल बैंकको नाफा २५ प्रतिशतले बढ्यो</span>
      <span id="ctl00_ContentPlaceHolder1_newsDate">May 07, 2020 07:57 PM</span>
      <div id="ctl00_ContentPlaceHolder1_newsDetail"><p>NABIL posted strong Q3 profit.</p></div>
    </body></html>
    """
    parsed = parse_merolagani_news_detail(html_full, 60000)
    assert parsed is not None
    assert parsed["news_id"] == 60000
    assert parsed["published_at"] == "2020-05-07"
    assert "नबिल" in parsed["title"]
    assert "NABIL" in parsed["content"]

    # Older format without timestamp ("May 01, 2018")
    html_old = """
    <span id="ctl00_ContentPlaceHolder1_newsTitle">Shree Investment net profit rises</span>
    <span id="ctl00_ContentPlaceHolder1_newsDate">May 01, 2018</span>
    """
    parsed_old = parse_merolagani_news_detail(html_old, 40000)
    assert parsed_old is not None
    assert parsed_old["published_at"] == "2018-05-01"

    # Malformed / tampered proxy HTML must return None
    assert parse_merolagani_news_detail("<html><body>Blocked</body></html>", 60001) is None
    assert parse_merolagani_news_detail("", 60002) is None


def test_informed_trading_signal_respects_causality_and_filters_pumps():
    prices = pd.DataFrame(
        [
            {"symbol": "NABIL", "date": pd.Timestamp("2024-05-09"), "close": 500.0, "volume": 10000},
            {"symbol": "NABIL", "date": pd.Timestamp("2024-05-10"), "close": 505.0, "volume": 12000},
            {"symbol": "PUMPX", "date": pd.Timestamp("2024-05-10"), "close": 300.0, "volume": 15000},
        ]
    )
    broker_df = pd.DataFrame(
        [
            # Valid prior-day accumulation for NABIL
            {
                "symbol": "NABIL", "date": pd.Timestamp("2024-05-09"),
                "hhi_buy_norm": 0.45, "hhi_sell_norm": 0.12,
                "circular_score": 0.05, "self_trade_pct": 0.01,
                "smart_money_score": 0.35, "pump_score": 0.0,
                "total_volume": 25000, "n_trades": 80,
                "top5_net_share": 0.42, "accumulation_score": 42.0,
                "pin_proxy": 0.30, "micro_score": 0.35, "kyle_significant": 1,
            },
            # Same-day row (must NOT be used for 2024-05-09)
            {
                "symbol": "NABIL", "date": pd.Timestamp("2024-05-10"),
                "hhi_buy_norm": 0.50, "hhi_sell_norm": 0.10,
                "circular_score": 0.02, "self_trade_pct": 0.0,
                "smart_money_score": 0.50, "pump_score": 0.0,
                "total_volume": 30000, "n_trades": 90,
                "top5_net_share": 0.50, "accumulation_score": 50.0,
                "pin_proxy": 0.35, "micro_score": 0.40, "kyle_significant": 1,
            },
            # Pump-flagged symbol (must be rejected)
            {
                "symbol": "PUMPX", "date": pd.Timestamp("2024-05-09"),
                "hhi_buy_norm": 0.60, "hhi_sell_norm": 0.10,
                "circular_score": 0.05, "self_trade_pct": 0.08,
                "smart_money_score": 0.40, "pump_score": 0.08,
                "total_volume": 25000, "n_trades": 80,
                "top5_net_share": 0.50, "accumulation_score": 50.0,
                "pin_proxy": 0.30, "micro_score": 0.30, "kyle_significant": 0,
            },
        ]
    )

    # On 2024-05-09, no prior-day broker rows exist -> must return empty (no lookahead)
    assert generate_informed_trading_signals_at_date(prices, broker_df, datetime(2024, 5, 9)) == []

    # On 2024-05-10, NABIL fires and PUMPX is rejected
    sigs = generate_informed_trading_signals_at_date(prices, broker_df, datetime(2024, 5, 10))
    assert [s.symbol for s in sigs] == ["NABIL"]
    assert sigs[0].direction == 1


def test_ipo_momentum_filters_non_ipo_when_table_present():
    dates = pd.date_range("2024-06-01", periods=10, freq="B")
    rows = []
    for sym in ("TESTA", "TESTB"):
        for i, d in enumerate(dates):
            rows.append({"symbol": sym, "date": d, "close": 100.0 + i * 5.0, "volume": 5000.0})
    prices = pd.DataFrame(rows)

    ipo_map = {
        "TESTA": {"issue_type": "IPO", "listing_date": "2024-06-01"},
        "TESTB": {"issue_type": "FPO", "listing_date": "2024-06-01"},
    }
    sigs = generate_ipo_momentum_signals_at_date(
        prices, dates[-1].to_pydatetime(), ipo_listings=ipo_map
    )
    assert [s.symbol for s in sigs] == ["TESTA"]
