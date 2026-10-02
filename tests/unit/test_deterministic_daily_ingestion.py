import sqlite3
from types import SimpleNamespace

import pandas as pd

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
    symbol_rows = conn.execute("SELECT COUNT(*) FROM ingestion_run_symbols").fetchone()[0]
    conn.close()

    assert run == ("PARTIAL", 0, 0)
    assert symbol_rows == 0
