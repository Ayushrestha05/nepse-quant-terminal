from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.quant_pro.data_fetch_issues import (
    ensure_issue_schema,
    list_issues,
    open_issue_symbols,
    record_issue,
    resolve_issues,
    retry_after_from_error,
)
import sqlite3


def _rate_limit_error(retry_after=None):
    error = RuntimeError("429 Too Many Requests")
    error.response = SimpleNamespace(status_code=429, headers={"Retry-After": retry_after} if retry_after else {})
    return error


def test_issue_attempts_resolve_to_history_and_retry_after_is_honored(tmp_path: Path):
    db_path = tmp_path / "issues.db"
    conn = sqlite3.connect(db_path)
    ensure_issue_schema(conn)
    record_issue(
        "merolagani", "history", "RATE_LIMITED", "too many requests", symbol="AAA",
        retry_after_utc=retry_after_from_error(_rate_limit_error("900")), conn=conn,
    )
    record_issue("merolagani", "history", "RATE_LIMITED", "deferred", symbol="BBB", attempts=0, conn=conn)
    conn.close()

    rows = list_issues(db_path=db_path)
    assert [(row["symbol"], row["attempts"], row["category"]) for row in rows] == [
        ("AAA", 1, "RATE_LIMITED"), ("BBB", 0, "RATE_LIMITED")
    ]
    deadline = datetime.fromisoformat(rows[0]["retry_after_utc"])
    assert timedelta(minutes=14) < deadline - datetime.now(timezone.utc) < timedelta(minutes=16)

    conn = sqlite3.connect(db_path)
    resolve_issues("merolagani", "history", symbols=["AAA"], conn=conn)
    event_count = conn.execute("SELECT COUNT(*) FROM data_fetch_issue_events").fetchone()[0]
    conn.close()
    assert [row["symbol"] for row in list_issues(db_path=db_path)] == ["BBB"]
    assert event_count == 3


def test_pending_legacy_resyncs_are_visible_as_issues(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE pending_full_resync(symbol TEXT, attempts INTEGER)")
    conn.execute("INSERT INTO pending_full_resync VALUES ('NABIL', 4)")
    conn.commit()
    conn.close()

    issue = list_issues(db_path=db_path)[0]
    assert issue["symbol"] == "NABIL"
    assert issue["category"] == "VENDOR_REBASE"
    assert issue["attempts"] == 4
    assert open_issue_symbols("history", db_path=db_path) == {"NABIL"}


def test_http_date_retry_after_and_default_cooldown():
    now = datetime.now(timezone.utc)
    error = _rate_limit_error("Tue, 03 Nov 2037 00:00:00 GMT")
    assert datetime.fromisoformat(retry_after_from_error(error)) == datetime(2037, 11, 3, tzinfo=timezone.utc)
    deadline = datetime.fromisoformat(retry_after_from_error(_rate_limit_error()))
    assert timedelta(minutes=14) < deadline - now < timedelta(minutes=16)
