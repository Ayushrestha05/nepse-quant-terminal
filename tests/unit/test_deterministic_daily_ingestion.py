import sqlite3
from types import SimpleNamespace

import pandas as pd
import requests

from scripts.ingestion import deterministic_daily_ingestion as ingestion


def _connection():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE stock_prices (
            symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL
        )"""
    )
    return conn


def _run(conn, symbols, **kwargs):
    return ingestion.execute_ingestion(
        conn=conn,
        symbols=symbols,
        source="test",
        history_days=365,
        backfill_days=5,
        max_staleness_days=7,
        sleep_ms=0,
        strict=False,
        **kwargs,
    )


def test_ingestion_keeps_per_symbol_failures_as_partial_result(monkeypatch):
    conn = _connection()
    monkeypatch.setattr(ingestion, "get_db_latest_market_date", lambda _conn: "2026-10-01")

    def fetch(symbol, *_args, **_kwargs):
        if symbol == "BAD":
            raise RuntimeError("vendor unavailable")
        return pd.DataFrame([{"Date": "2026-10-02", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100}])

    monkeypatch.setattr(ingestion, "fetch_symbol_history", fetch)
    monkeypatch.setattr(ingestion, "save_to_db", lambda *_args, **_kwargs: SimpleNamespace(rebase_detected=False))

    assert _run(conn, ["GOOD", "BAD"]) == 0
    run = conn.execute("SELECT status, symbols_succeeded, symbols_failed FROM ingestion_runs").fetchone()
    outcomes = conn.execute("SELECT symbol, status, error FROM ingestion_run_symbols ORDER BY symbol").fetchall()
    conn.close()

    assert run == ("PARTIAL", 1, 1)
    assert outcomes == [("BAD", "FAILED", "vendor unavailable"), ("GOOD", "SUCCESS", None)]


def test_ingestion_cancel_file_stops_before_next_symbol(tmp_path, monkeypatch):
    conn = _connection()
    cancel_file = tmp_path / "cancel.flag"
    cancel_file.write_text("cancel", encoding="utf-8")
    monkeypatch.setattr(ingestion, "get_db_latest_market_date", lambda _conn: None)

    assert _run(conn, ["NEVER_FETCH"], cancel_file=cancel_file) == 0
    run = conn.execute("SELECT status, symbols_succeeded, symbols_failed FROM ingestion_runs").fetchone()
    symbol_rows = conn.execute("SELECT symbol,status,error FROM ingestion_run_symbols").fetchall()
    issue = conn.execute("SELECT category,status FROM data_fetch_issues WHERE symbol='NEVER_FETCH'").fetchone()
    conn.close()

    assert run == ("PARTIAL", 0, 1)
    assert symbol_rows == [("NEVER_FETCH", "FAILED", "cancelled_before_fetch")]
    assert issue == ("CANCELLED", "OPEN")


def test_ingestion_cancel_after_current_symbol_queues_remaining_work(tmp_path, monkeypatch):
    conn = _connection()
    cancel_file = tmp_path / "cancel.flag"
    monkeypatch.setattr(ingestion, "get_db_latest_market_date", lambda _conn: "2026-10-02")

    def fetch(symbol, *_args, **_kwargs):
        if symbol == "AAA":
            cancel_file.write_text("cancel", encoding="utf-8")
        return pd.DataFrame([{"Date": "2026-10-02", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 1}])

    monkeypatch.setattr(ingestion, "fetch_symbol_history", fetch)
    monkeypatch.setattr(ingestion, "save_to_db", lambda *_args, **_kwargs: SimpleNamespace(rebase_detected=False))

    _run(conn, ["AAA", "BBB"], cancel_file=cancel_file)
    rows = conn.execute("SELECT symbol,status,error FROM ingestion_run_symbols ORDER BY symbol").fetchall()
    issue = conn.execute("SELECT category FROM data_fetch_issues WHERE symbol='BBB'").fetchone()
    conn.close()

    assert rows == [("AAA", "SUCCESS", None), ("BBB", "FAILED", "cancelled_before_fetch")]
    assert issue == ("CANCELLED",)


def test_ingestion_429_stops_batch_and_persists_cooldown_for_remaining_symbols(monkeypatch):
    conn = _connection()
    monkeypatch.setattr(ingestion, "get_db_latest_market_date", lambda _conn: "2026-10-02")
    calls = []

    def fetch(symbol, *_args, **_kwargs):
        calls.append(symbol)
        error = requests.HTTPError("429 Too Many Requests")
        error.response = SimpleNamespace(status_code=429, headers={"Retry-After": "900"})
        raise error

    monkeypatch.setattr(ingestion, "fetch_symbol_history", fetch)
    assert _run(conn, ["AAA", "BBB", "CCC"]) == 0
    issues = conn.execute(
        "SELECT symbol,category,attempts,retry_after_utc FROM data_fetch_issues ORDER BY symbol"
    ).fetchall()
    run = conn.execute("SELECT status,symbols_failed FROM ingestion_runs").fetchone()
    conn.close()

    assert calls == ["AAA"]
    assert run == ("PARTIAL", 3)
    assert [row[:3] for row in issues] == [
        ("AAA", "RATE_LIMITED", 1), ("BBB", "RATE_LIMITED", 0), ("CCC", "RATE_LIMITED", 0)
    ]
    assert all(row[3] for row in issues)


def test_successful_history_retry_resolves_the_open_issue(monkeypatch):
    conn = _connection()
    monkeypatch.setattr(ingestion, "get_db_latest_market_date", lambda _conn: "2026-10-02")
    from backend.quant_pro.data_fetch_issues import record_issue

    record_issue("merolagani", "history", "NETWORK", "offline", symbol="AAA", conn=conn)
    monkeypatch.setattr(ingestion, "fetch_symbol_history", lambda *_args, **_kwargs: pd.DataFrame([
        {"Date": "2026-10-02", "Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 100}
    ]))
    monkeypatch.setattr(ingestion, "save_to_db", lambda *_args, **_kwargs: SimpleNamespace(rebase_detected=False))

    assert _run(conn, ["AAA"]) == 0
    assert conn.execute("SELECT status FROM data_fetch_issues WHERE symbol='AAA'").fetchone() == ("RESOLVED",)
    assert conn.execute("SELECT COUNT(*) FROM data_fetch_issue_events WHERE status='RESOLVED'").fetchone()[0] == 1
    conn.close()
