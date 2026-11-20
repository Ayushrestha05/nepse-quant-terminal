"""Dedicated SQLite store (`data/backtests.db`) for backtest runs, trades, NAV, and deposits.

Keeps every historical run (append-only) and exposes `has_run(...)` so runners
skip unchanged `(strategy_id, scenario, config_hash, data_end, window)` combos
unless `--force` is passed.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.backtesting.simple_backtest import (
    NEPSE_TRADING_DAYS,
    BacktestResult,
    compute_xirr,
)
from backend.quant_pro.paths import ensure_dir, get_project_root

PROJECT_ROOT = get_project_root(__file__)
DEFAULT_BACKTESTS_DB = PROJECT_ROOT / "data" / "backtests.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    scenario TEXT NOT NULL,
    config_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    data_end TEXT NOT NULL,
    git_sha TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    in_sample_metrics_json TEXT NOT NULL,
    out_of_sample_metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_lookup
    ON runs (strategy_id, scenario, config_hash, data_end, start_date, end_date);

CREATE TABLE IF NOT EXISTS trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    signal_date TEXT,
    entry_date TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_date TEXT,
    exit_price REAL,
    shares INTEGER NOT NULL,
    position_value REAL NOT NULL,
    buy_fees REAL NOT NULL,
    sell_fees REAL NOT NULL,
    gross_pnl REAL,
    net_pnl REAL,
    gross_return REAL,
    net_return REAL,
    holding_days INTEGER,
    signal_type TEXT NOT NULL,
    direction INTEGER NOT NULL,
    exit_reason TEXT NOT NULL,
    max_price REAL NOT NULL,
    target_exit_date TEXT,
    max_holding_days INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_run ON trades (run_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol, entry_date);

CREATE TABLE IF NOT EXISTS daily_nav (
    run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    nav REAL NOT NULL,
    cash REAL NOT NULL,
    invested REAL NOT NULL,
    PRIMARY KEY (run_id, date)
);

CREATE TABLE IF NOT EXISTS contributions (
    contrib_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    amount REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contributions_run ON contributions (run_id);
"""


def get_backtests_db_path(db_path: Optional[Path] = None) -> Path:
    path = Path(db_path) if db_path is not None else DEFAULT_BACKTESTS_DB
    ensure_dir(path.parent)
    return path


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = get_backtests_db_path(db_path)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    return conn


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    return str(dt)[:10]


def config_hash(config: Dict[str, Any]) -> str:
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def current_git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def compute_window_metrics(
    result: BacktestResult,
    start_inclusive: Optional[str] = None,
    end_inclusive: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute TWR, XIRR, Sharpe, MaxDD, fees, and trade stats on a date sub-window."""
    start_ts = pd.Timestamp(start_inclusive) if start_inclusive else None
    end_ts = pd.Timestamp(end_inclusive) if end_inclusive else None

    nav_rows = [
        (pd.Timestamp(d), float(v))
        for d, v in result.daily_nav
        if (start_ts is None or pd.Timestamp(d) >= start_ts)
        and (end_ts is None or pd.Timestamp(d) <= end_ts)
    ]
    if len(nav_rows) < 2:
        return {
            "trading_days": len(nav_rows),
            "start_nav": nav_rows[0][1] if nav_rows else 0.0,
            "final_nav": nav_rows[-1][1] if nav_rows else 0.0,
            "total_contributed": 0.0,
            "twr_total_return_pct": 0.0,
            "twr_cagr_pct": 0.0,
            "xirr_pct": None,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown_pct": 0.0,
            "trades": 0,
            "win_rate_pct": 0.0,
            "total_fees": 0.0,
            "fees_pct_of_contributed": 0.0,
        }

    win_start = nav_rows[0][0]
    win_end = nav_rows[-1][0]
    contrib_by_day: Dict[pd.Timestamp, float] = {}
    win_contribs: List[Tuple[pd.Timestamp, float]] = []
    for dt, amt in result.contributions:
        ts = pd.Timestamp(dt).normalize()
        if win_start < ts <= win_end:
            contrib_by_day[ts] = contrib_by_day.get(ts, 0.0) + float(amt)
            win_contribs.append((ts, float(amt)))

    rets: List[float] = []
    for idx in range(1, len(nav_rows)):
        prev_nav = nav_rows[idx - 1][1]
        cur_dt, cur_nav = nav_rows[idx]
        cf = contrib_by_day.get(cur_dt.normalize(), 0.0)
        denom = prev_nav + cf
        rets.append((cur_nav / denom - 1.0) if denom > 0 else 0.0)
    rets_arr = np.array(rets, dtype=float)
    twr_curve = np.concatenate(([1.0], np.cumprod(1.0 + rets_arr)))
    twr_total = float(twr_curve[-1] - 1.0)
    cal_days = max(1, (win_end - win_start).days)
    twr_cagr = float((1.0 + twr_total) ** (365.0 / cal_days) - 1.0) if twr_total > -1.0 else -1.0

    std = float(np.std(rets_arr, ddof=1)) if len(rets_arr) >= 30 else 0.0
    sharpe = float(np.mean(rets_arr) / std * np.sqrt(NEPSE_TRADING_DAYS)) if std > 0 else 0.0
    down = rets_arr[rets_arr < 0]
    down_std = float(np.std(down, ddof=1)) if len(down) >= 2 else 0.0
    sortino = float(np.mean(rets_arr) / down_std * np.sqrt(NEPSE_TRADING_DAYS)) if down_std > 0 else 0.0

    run_max = np.maximum.accumulate(twr_curve)
    max_dd = float(np.min((twr_curve - run_max) / run_max))

    # Money-weighted XIRR across the window (treating start_nav as initial investment)
    start_nav = nav_rows[0][1]
    final_nav = nav_rows[-1][1]
    flows: List[Tuple[Any, float]] = [(win_start, -start_nav)]
    for dt, amt in win_contribs:
        flows.append((dt, -amt))
    flows.append((win_end, final_nav))
    xirr_val = compute_xirr(flows)

    # Trades whose exit_date falls inside the window (or entry_date if full window)
    win_trades = [
        t for t in result.completed_trades
        if t.exit_date is not None
        and win_start <= pd.Timestamp(t.exit_date) <= win_end
    ]
    n_trades = len(win_trades)
    wins = sum(1 for t in win_trades if (t.net_pnl or 0.0) > 0)
    total_fees = sum(float(t.buy_fees + t.sell_fees) for t in win_trades)
    total_contributed = (
        result.total_contributed
        if start_ts is None and end_ts is None
        else start_nav + sum(amt for _, amt in win_contribs)
    )
    fees_pct = (total_fees / total_contributed * 100.0) if total_contributed > 0 else 0.0

    return {
        "trading_days": len(nav_rows),
        "start_nav": round(start_nav, 2),
        "final_nav": round(final_nav, 2),
        "total_contributed": round(total_contributed, 2),
        "twr_total_return_pct": round(twr_total * 100.0, 2),
        "twr_cagr_pct": round(twr_cagr * 100.0, 2),
        "xirr_pct": round(xirr_val * 100.0, 2) if xirr_val is not None else None,
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "trades": n_trades,
        "win_rate_pct": round((wins / n_trades * 100.0) if n_trades else 0.0, 1),
        "total_fees": round(total_fees, 2),
        "fees_pct_of_contributed": round(fees_pct, 2),
    }


def has_run(
    *,
    strategy_id: str,
    scenario: str,
    config: Dict[str, Any],
    data_end: str,
    start_date: str,
    end_date: str,
    db_path: Optional[Path] = None,
) -> Optional[int]:
    """Return existing `run_id` if an identical run already exists in `data/backtests.db`."""
    chash = config_hash(config)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT run_id FROM runs
            WHERE strategy_id = ? AND scenario = ? AND config_hash = ?
              AND data_end = ? AND start_date = ? AND end_date = ?
            ORDER BY run_id DESC LIMIT 1
            """,
            (strategy_id, scenario, chash, data_end, start_date, end_date),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def save_run(
    *,
    strategy_id: str,
    scenario: str,
    config: Dict[str, Any],
    result: BacktestResult,
    data_end: str,
    in_sample_end: str = "2024-12-31",
    out_of_sample_start: str = "2025-01-01",
    db_path: Optional[Path] = None,
) -> int:
    """Persist a completed backtest run (metadata, trades, daily NAV, contributions)."""
    chash = config_hash(config)
    full_metrics = compute_window_metrics(result)
    is_metrics = compute_window_metrics(result, end_inclusive=in_sample_end)
    oos_metrics = compute_window_metrics(result, start_inclusive=out_of_sample_start)

    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO runs (
                strategy_id, scenario, config_json, config_hash, data_end,
                git_sha, start_date, end_date, metrics_json,
                in_sample_metrics_json, out_of_sample_metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_id,
                scenario,
                json.dumps(config, sort_keys=True, default=str),
                chash,
                data_end,
                current_git_sha(),
                _iso(result.start_date) or "",
                _iso(result.end_date) or "",
                json.dumps(full_metrics, sort_keys=True),
                json.dumps(is_metrics, sort_keys=True),
                json.dumps(oos_metrics, sort_keys=True),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        run_id = int(cur.lastrowid)

        trade_rows = [
            (
                run_id,
                t.symbol,
                _iso(t.signal_date),
                _iso(t.entry_date) or "",
                float(t.entry_price),
                _iso(t.exit_date),
                float(t.exit_price) if t.exit_price is not None else None,
                int(t.shares),
                float(t.position_value),
                float(t.buy_fees),
                float(t.sell_fees),
                float(t.gross_pnl) if t.gross_pnl is not None else None,
                float(t.net_pnl) if t.net_pnl is not None else None,
                float(t.gross_return) if t.gross_return is not None else None,
                float(t.net_return) if t.net_return is not None else None,
                int(t.holding_days) if t.holding_days is not None else None,
                str(t.signal_type or ""),
                int(t.direction),
                str(t.exit_reason or ""),
                float(t.max_price),
                _iso(t.target_exit_date),
                int(t.max_holding_days),
            )
            for t in result.trades
        ]
        if trade_rows:
            cur.executemany(
                """
                INSERT INTO trades (
                    run_id, symbol, signal_date, entry_date, entry_price,
                    exit_date, exit_price, shares, position_value,
                    buy_fees, sell_fees, gross_pnl, net_pnl,
                    gross_return, net_return, holding_days,
                    signal_type, direction, exit_reason, max_price,
                    target_exit_date, max_holding_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                trade_rows,
            )

        if result.daily_nav_detail:
            nav_rows = [
                (run_id, _iso(d) or "", float(nav), float(cash), float(inv))
                for d, nav, cash, inv in result.daily_nav_detail
            ]
        else:
            nav_rows = [
                (run_id, _iso(d) or "", float(nav), 0.0, float(nav))
                for d, nav in result.daily_nav
            ]
        if nav_rows:
            cur.executemany(
                "INSERT INTO daily_nav (run_id, date, nav, cash, invested) VALUES (?, ?, ?, ?, ?)",
                nav_rows,
            )

        if result.contributions:
            cur.executemany(
                "INSERT INTO contributions (run_id, date, amount) VALUES (?, ?, ?)",
                [(run_id, _iso(d) or "", float(amt)) for d, amt in result.contributions],
            )

        conn.commit()
        return run_id
    finally:
        conn.close()


def load_latest_runs(
    *,
    data_end: Optional[str] = None,
    strategy_ids: Optional[List[str]] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return the most recent run per `(strategy_id, scenario)`."""
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        clauses: List[str] = []
        params: List[Any] = []
        if data_end:
            clauses.append("data_end = ?")
            params.append(data_end)
        if strategy_ids:
            placeholders = ",".join("?" for _ in strategy_ids)
            clauses.append(f"strategy_id IN ({placeholders})")
            params.extend(strategy_ids)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM runs {where} ORDER BY run_id DESC",
            params,
        ).fetchall()
        seen: set[Tuple[str, str]] = set()
        out: List[Dict[str, Any]] = []
        for r in rows:
            key = (r["strategy_id"], r["scenario"])
            if key in seen:
                continue
            seen.add(key)
            item = dict(r)
            item["config"] = json.loads(item["config_json"])
            item["metrics"] = json.loads(item["metrics_json"])
            item["in_sample_metrics"] = json.loads(item["in_sample_metrics_json"])
            item["out_of_sample_metrics"] = json.loads(item["out_of_sample_metrics_json"])
            out.append(item)
        return out
    finally:
        conn.close()


def load_run_nav(run_id: int, db_path: Optional[Path] = None) -> pd.DataFrame:
    conn = _connect(db_path)
    try:
        return pd.read_sql_query(
            "SELECT date, nav, cash, invested FROM daily_nav WHERE run_id = ? ORDER BY date",
            conn,
            params=(run_id,),
            parse_dates=["date"],
        )
    finally:
        conn.close()


def load_run_trades(run_id: int, db_path: Optional[Path] = None) -> pd.DataFrame:
    conn = _connect(db_path)
    try:
        return pd.read_sql_query(
            "SELECT * FROM trades WHERE run_id = ? ORDER BY entry_date, symbol",
            conn,
            params=(run_id,),
        )
    finally:
        conn.close()
