"""Persistent current-state issues from market data fetches."""

from __future__ import annotations

import email.utils
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


def _db_path(db_path: Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    from backend.quant_pro.database import get_db_path

    return get_db_path()


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path(db_path)), timeout=30)
    ensure_issue_schema(conn)
    return conn


def ensure_issue_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS data_fetch_issues (
            issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            operation TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            detail TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            attempts INTEGER NOT NULL DEFAULT 1,
            first_seen_utc TEXT NOT NULL,
            last_attempt_utc TEXT NOT NULL,
            retry_after_utc TEXT,
            run_id INTEGER,
            UNIQUE(source, operation, symbol, category)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_data_fetch_issues_status_retry "
        "ON data_fetch_issues(status, retry_after_utc)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS data_fetch_issue_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            operation TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL,
            attempted_at_utc TEXT NOT NULL,
            retry_after_utc TEXT,
            run_id INTEGER
        )"""
    )


def record_issue(
    source: str,
    operation: str,
    category: str,
    detail: str,
    *,
    symbol: str = "",
    retry_after_utc: str | None = None,
    run_id: int | None = None,
    status: str = "OPEN",
    attempts: int = 1,
    db_path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    owns_connection = conn is None
    conn = _connect(db_path) if conn is None else conn
    ensure_issue_schema(conn)
    try:
        conn.execute(
            """INSERT INTO data_fetch_issues (
                source,operation,symbol,category,detail,status,attempts,
                first_seen_utc,last_attempt_utc,retry_after_utc,run_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source,operation,symbol,category) DO UPDATE SET
                detail=excluded.detail,
                status=excluded.status,
                attempts=data_fetch_issues.attempts + excluded.attempts,
                last_attempt_utc=excluded.last_attempt_utc,
                retry_after_utc=excluded.retry_after_utc,
                run_id=excluded.run_id""",
            (source, operation, symbol or "", category, detail, status, attempts,
             now, now, retry_after_utc, run_id),
        )
        conn.execute(
            """INSERT INTO data_fetch_issue_events (
                source,operation,symbol,category,status,detail,attempted_at_utc,retry_after_utc,run_id
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (source, operation, symbol or "", category, status, detail, now, retry_after_utc, run_id),
        )
        conn.commit()
    finally:
        if owns_connection:
            conn.close()


def ensure_pending_resync_issues(db_path: Path | None = None) -> None:
    """Expose the legacy full-resync queue in the unified Issues view."""
    conn = _connect(db_path)
    try:
        try:
            rows = conn.execute(
                "SELECT symbol,attempts FROM pending_full_resync ORDER BY symbol"
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn.executemany(
            """INSERT INTO data_fetch_issues (
                source,operation,symbol,category,detail,status,attempts,
                first_seen_utc,last_attempt_utc
            ) VALUES ('merolagani','history',?,'VENDOR_REBASE',
                'Provider changed previously stored prices; full history resync is pending.',
                'OPEN',?,?,?)
            ON CONFLICT(source,operation,symbol,category) DO NOTHING""",
            [(symbol, int(attempts), now, now) for symbol, attempts in rows],
        )
        conn.commit()
    finally:
        conn.close()


def list_issues(
    *, include_resolved: bool = False, eligible_only: bool = False, db_path: Path | None = None
) -> list[dict]:
    ensure_pending_resync_issues(db_path)
    conn = _connect(db_path)
    try:
        query = (
            "SELECT issue_id,source,operation,symbol,category,detail,status,attempts,"
            "last_attempt_utc,retry_after_utc,run_id FROM data_fetch_issues"
        )
        if not include_resolved:
            query += " WHERE status!='RESOLVED'"
        if eligible_only:
            query += " AND (retry_after_utc IS NULL OR retry_after_utc<=?)" if " WHERE " in query else " WHERE retry_after_utc IS NULL OR retry_after_utc<=?"
            params = (datetime.now(timezone.utc).replace(microsecond=0).isoformat(),)
        else:
            params = ()
        query += " ORDER BY CASE status WHEN 'OPEN' THEN 0 WHEN 'DEGRADED' THEN 1 ELSE 2 END, last_attempt_utc DESC, symbol"
        columns = (
            "issue_id", "source", "operation", "symbol", "category", "detail", "status",
            "attempts", "last_attempt_utc", "retry_after_utc", "run_id",
        )
        return [dict(zip(columns, row)) for row in conn.execute(query, params)]
    finally:
        conn.close()


def open_issue_symbols(operation: str, *, db_path: Path | None = None) -> set[str]:
    ensure_pending_resync_issues(db_path)
    conn = _connect(db_path)
    try:
        return {
            str(row[0]) for row in conn.execute(
                "SELECT DISTINCT symbol FROM data_fetch_issues "
                "WHERE operation=? AND status!='RESOLVED' AND symbol!=''",
                (operation,),
            )
        }
    finally:
        conn.close()


def resolve_issues(
    source: str,
    operation: str,
    *,
    symbols: Iterable[str] | None = None,
    db_path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    owns_connection = conn is None
    conn = _connect(db_path) if conn is None else conn
    ensure_issue_schema(conn)
    try:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        if symbols is None:
            rows = conn.execute(
                "SELECT source,operation,symbol,category,detail FROM data_fetch_issues "
                "WHERE source=? AND operation=? AND status!='RESOLVED'", (source, operation),
            ).fetchall()
            conn.execute(
                "UPDATE data_fetch_issues SET status='RESOLVED',retry_after_utc=NULL,last_attempt_utc=? "
                "WHERE source=? AND operation=? AND status!='RESOLVED'",
                (now, source, operation),
            )
        else:
            clean = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
            if clean:
                placeholders = ",".join("?" for _ in clean)
                rows = conn.execute(
                    "SELECT source,operation,symbol,category,detail FROM data_fetch_issues "
                    f"WHERE source=? AND operation=? AND symbol IN ({placeholders}) AND status!='RESOLVED'",
                    (source, operation, *clean),
                ).fetchall()
                conn.execute(
                    "UPDATE data_fetch_issues SET status='RESOLVED',retry_after_utc=NULL,last_attempt_utc=? "
                    f"WHERE source=? AND operation=? AND symbol IN ({placeholders}) AND status!='RESOLVED'",
                    (now, source, operation, *clean),
                )
            else:
                rows = []
        conn.executemany(
            """INSERT INTO data_fetch_issue_events (
                source,operation,symbol,category,status,detail,attempted_at_utc
            ) VALUES (?,?,?,?, 'RESOLVED', ?, ?)""",
            [(src, op, sym, category, detail, now) for src, op, sym, category, detail in rows],
        )
        conn.commit()
    finally:
        if owns_connection:
            conn.close()


def retry_after_from_error(exc: BaseException, *, default_minutes: int = 15) -> str | None:
    response = getattr(exc, "response", None)
    if response is None or getattr(response, "status_code", None) != 429:
        return None
    header = getattr(response, "headers", {}).get("Retry-After")
    now = datetime.now(timezone.utc)
    if header:
        try:
            deadline = now + timedelta(seconds=max(0, int(header)))
        except (TypeError, ValueError):
            try:
                deadline = email.utils.parsedate_to_datetime(header)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                deadline = deadline.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                deadline = now + timedelta(minutes=default_minutes)
    else:
        deadline = now + timedelta(minutes=default_minutes)
    return deadline.replace(microsecond=0).isoformat()


def classify_fetch_error(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code is not None:
        return "HTTP_ERROR" if status_code >= 400 else "INVALID_RESPONSE"
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "TIMEOUT"
    if "request" in name or "connection" in name:
        return "NETWORK"
    if isinstance(exc, (ValueError, KeyError)):
        return "INVALID_RESPONSE"
    return "OTHER"


def is_rate_limited(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429
