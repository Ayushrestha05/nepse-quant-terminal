import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.desktop.dashboard import DesktopDashboard, _number


def test_number_input_accepts_finite_values_and_rejects_invalid_values():
    assert _number("1,234.5") == 1234.5
    assert _number("", fallback=2.0) == 2.0
    for value in ("abc", "nan", "inf"):
        with pytest.raises(ValueError):
            _number(value)


def test_market_coverage_reports_missing_months_and_benchmark_date(tmp_path: Path):
    db_path = tmp_path / "market.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE stock_prices (symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    conn.execute("CREATE TABLE market_quotes (symbol TEXT,fetched_at_utc TEXT)")
    conn.executemany(
        "INSERT INTO stock_prices (symbol,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        [
            ("AAA", "2026-04-15", 100, 100, 100, 100, 10),
            ("AAA", "2026-10-02", 110, 110, 110, 110, 10),
            ("NEPSE", "2026-04-15", 2700, 2700, 2700, 2700, 10),
        ],
    )
    conn.execute("INSERT INTO market_quotes VALUES ('AAA','2026-10-02T17:46:27+00:00')")
    conn.commit()
    conn.close()

    report = DesktopDashboard._market_coverage(db_path)

    assert "2026-04-15" in report
    assert "2026-10-02 · 1 symbols" in report
    assert "2026-05, 2026-06, 2026-07, 2026-08, 2026-09" in report


def test_all_stored_market_view_includes_old_symbols_and_blanks_stale_changes(tmp_path: Path):
    db_path = tmp_path / "market.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE stock_prices (symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    conn.executemany(
        "INSERT INTO stock_prices (symbol,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        [
            ("AAA", "2026-04-15", 100, 100, 100, 100, 10),
            ("AAA", "2026-10-01", 109, 109, 109, 110, 10),
            ("BBB", "2026-04-15", 50, 50, 50, 50, 10),
            ("NEPSE", "2026-04-15", 2700, 2700, 2700, 2700, 10),
            ("SECTOR::BANK", "2026-10-01", 100, 100, 100, 100, 10),
        ],
    )
    conn.commit()
    conn.close()

    rows = DesktopDashboard._load_all_stored_market(SimpleNamespace(_db_path=lambda: db_path))
    indexed = {row["symbol"]: row for row in rows}

    assert set(indexed) == {"AAA", "BBB"}
    assert indexed["AAA"]["date"] == "2026-10-01"
    assert indexed["AAA"]["chg"] is None
    assert indexed["BBB"]["date"] == "2026-04-15"


def test_rates_keep_available_sources_when_other_sources_fail(monkeypatch):
    from apps.tui.io import fetchers
    from backend.market import kalimati_market

    monkeypatch.setattr(kalimati_market, "init_kalimati_db", lambda: None)
    monkeypatch.setattr(kalimati_market, "refresh_kalimati", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(fetchers, "_fetch_gold_silver_prices", lambda: (_ for _ in ()).throw(RuntimeError("timeout")))
    monkeypatch.setattr(fetchers, "_fetch_noc_fuel_prices", lambda: {"petrol": 180, "date_bs": "today"})
    monkeypatch.setattr(fetchers, "_fetch_yahoo_futures_price", lambda *_args: None)
    monkeypatch.setattr(fetchers, "_fetch_nrb_forex_rates", lambda: [{"currency_code": "USD", "sell_rate": 135}])

    result = DesktopDashboard._load_rates(SimpleNamespace())

    assert [row["item"] for row in result["rows"]] == ["NOC Petrol", "NPR / USD"]
    assert "2 sources unavailable" in result["status"]
    assert "Kalimati: offline" in result["detail"]
    assert "Gold and silver: timeout" in result["detail"]


def test_rates_report_optional_source_failures_when_kalimati_succeeds(monkeypatch):
    from apps.tui.io import fetchers
    from backend.market import kalimati_market

    monkeypatch.setattr(kalimati_market, "init_kalimati_db", lambda: None)
    monkeypatch.setattr(kalimati_market, "refresh_kalimati", lambda: ([{"name_english": "Rice", "avg": 90}], "Kalimati updated"))
    monkeypatch.setattr(fetchers, "_fetch_gold_silver_prices", lambda: (_ for _ in ()).throw(RuntimeError("timeout")))
    monkeypatch.setattr(fetchers, "_fetch_noc_fuel_prices", lambda: {})
    monkeypatch.setattr(fetchers, "_fetch_yahoo_futures_price", lambda *_args: None)
    monkeypatch.setattr(fetchers, "_fetch_nrb_forex_rates", lambda: [])

    result = DesktopDashboard._load_rates(SimpleNamespace())

    assert result["status"] == "Kalimati updated · 1 market rates · 1 sources unavailable"
    assert "Gold and silver: timeout" in result["detail"]
