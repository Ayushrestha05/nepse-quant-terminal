"""Shared "already in DB?" helpers for ingest pipelines.

Use before HTTP so scrapers/APIs do not re-download what we already stored.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Sequence


def _connect(db_path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path), timeout=60)


def max_stored_date(
    db_path: str | Path,
    sql: str,
    params: Sequence[Any] = (),
) -> Optional[str]:
    """Run a SELECT that returns one date string (YYYY-MM-DD) or None."""
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row or row[0] is None:
        return None
    return str(row[0])[:10]


def has_rows(
    db_path: str | Path,
    sql: str,
    params: Sequence[Any] = (),
) -> bool:
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    if not row:
        return False
    return int(row[0] or 0) > 0


def next_day(date_str: str) -> str:
    return (datetime.strptime(date_str[:10], "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def incremental_start(
    db_path: str | Path,
    *,
    sql: str,
    params: Sequence[Any] = (),
    fallback_start: str,
) -> str:
    """Return max(stored)+1 day, or fallback_start when empty."""
    last = max_stored_date(db_path, sql, params)
    if not last:
        return fallback_start
    return next_day(last)
