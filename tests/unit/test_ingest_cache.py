"""Checks for ingest skip/incremental helpers."""

from __future__ import annotations

import sqlite3

from backend.quant_pro.ingest_cache import has_rows, incremental_start, max_stored_date, next_day


def test_max_stored_date_and_incremental(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (date TEXT)")
    conn.execute("INSERT INTO t VALUES ('2026-01-10'), ('2026-01-12')")
    conn.commit()
    conn.close()

    assert max_stored_date(db, "SELECT MAX(date) FROM t") == "2026-01-12"
    assert next_day("2026-01-12") == "2026-01-13"
    assert incremental_start(db, sql="SELECT MAX(date) FROM t", fallback_start="2020-01-01") == "2026-01-13"
    assert has_rows(db, "SELECT COUNT(*) FROM t WHERE date = ?", ("2026-01-12",))
    assert not has_rows(db, "SELECT COUNT(*) FROM t WHERE date = ?", ("2099-01-01",))


def test_incremental_start_empty_uses_fallback(tmp_path):
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (date TEXT)")
    conn.commit()
    conn.close()
    assert incremental_start(db, sql="SELECT MAX(date) FROM t", fallback_start="2020-01-01") == "2020-01-01"
