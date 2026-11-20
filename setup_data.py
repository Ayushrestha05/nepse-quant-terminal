#!/usr/bin/env python3
"""
NEPSE Quant Terminal — Initial data setup.

Downloads the pre-built database from the GitHub release (fast, ~13 MB),
or falls back to scraping from Merolagani if preferred.

Usage:
    python setup_data.py               # download pre-built DB (recommended)
    python setup_data.py --scrape      # scrape fresh from Merolagani instead
    python setup_data.py --scrape --days 90   # scrape only last 90 days
    python setup_data.py --symbol NABIL       # scrape a single symbol
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 14):
    print(
        "ERROR: Python 3.14+ is not yet supported.\n"
        "The nepse package and numba both cap at Python <3.14.\n"
        "Please use Python 3.10 – 3.13 (recommended: 3.12).\n"
        "  pyenv install 3.12 && pyenv local 3.12"
    )
    sys.exit(1)

import argparse
import gzip
import shutil
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

DB_RELEASE_URL = (
    "https://github.com/nlethetech/nepse-quant-terminal"
    "/releases/download/v3.0/nepse_data_public.db.gz"
)
ALL_SYMBOLS_FILE = Path(__file__).parent / "all_symbols.txt"
DELAY_BETWEEN_SYMBOLS = 1.2  # seconds — stay under Merolagani rate limit


# ── helpers ───────────────────────────────────────────────────────────────────

def _db_path() -> Path:
    from backend.quant_pro.database import get_db_path
    return Path(get_db_path())


def _progress(count, block_size, total_size):
    pct = min(int(count * block_size * 100 / total_size), 100) if total_size > 0 else 0
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(f"\r  [{bar}] {pct}%", end="", flush=True)


# ── download path ─────────────────────────────────────────────────────────────

def download_db():
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    gz_path = db_path.parent / "nepse_data_public.db.gz"

    print(f"Downloading pre-built database from GitHub release...")
    print(f"  {DB_RELEASE_URL}")
    try:
        urllib.request.urlretrieve(DB_RELEASE_URL, gz_path, _progress)
        print()
    except Exception as e:
        print(f"\nERROR: download failed: {e}")
        print("Try --scrape to fetch data directly from Merolagani instead.")
        return False

    print(f"Extracting to {db_path} ...")
    with gzip.open(gz_path, "rb") as f_in, open(db_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    gz_path.unlink()

    # Quick sanity check
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT COUNT(*) FROM stock_prices").fetchone()[0]
    conn.close()
    print(f"Done — {rows:,} price rows in {db_path}  ({db_path.stat().st_size // 1_000_000} MB)")
    return True


# ── scrape path ───────────────────────────────────────────────────────────────

def load_symbols() -> list[str]:
    if ALL_SYMBOLS_FILE.exists():
        from backend.quant_pro.signal_ranking import is_tradeable_signal_symbol
        syms = [s.strip() for s in ALL_SYMBOLS_FILE.read_text().splitlines() if s.strip()]
        filtered = [s for s in syms if is_tradeable_signal_symbol(s)]
        if "NEPSE" not in filtered:
            filtered.append("NEPSE")
        return filtered
    return ["NEPSE"]


def ts(dt: datetime) -> int:
    return int(dt.timestamp())


def backfill_symbol(symbol: str, start: datetime, end: datetime) -> int:
    from backend.quant_pro.database import save_to_db
    from backend.quant_pro.data_io import resync_full_history
    from backend.quant_pro.vendor_api import fetch_ohlcv_chunk
    try:
        df = fetch_ohlcv_chunk(symbol, ts(start), ts(end))
        if df is None or df.empty:
            return 0
        df["symbol"] = symbol
        # This fetches a rolling window over a possibly-deep DB, so a re-base
        # written in log mode would splice at the window boundary. Abort instead
        # and re-fetch the whole series on the new basis.
        result = save_to_db(df, symbol, on_rebase="abort")
        if result.rebase_detected:
            resync_full_history(symbol)
        return len(df)
    except Exception as e:
        print(f"  WARN {symbol}: {e}")
        return 0


def scrape_db(days: int, symbol: str | None):
    from backend.quant_pro.database import get_db_path, init_db
    print("Initialising database...")
    init_db()

    end   = datetime.now()
    start = end - timedelta(days=days)
    symbols = [symbol] if symbol else load_symbols()

    if not symbols:
        print("ERROR: no symbols found. Check all_symbols.txt exists.")
        return

    print(f"Scraping {len(symbols)} symbols from Merolagani  |  {start.date()} → {end.date()}")
    print(f"DB: {get_db_path()}\n")

    total = 0
    for i, sym in enumerate(symbols, 1):
        rows = backfill_symbol(sym, start, end)
        total += rows
        print(f"[{i:3d}/{len(symbols)}] {sym:<12} {rows:>5} rows")
        if i < len(symbols):
            time.sleep(DELAY_BETWEEN_SYMBOLS)

    print(f"\nDone — {total:,} rows written to {get_db_path()}")


def backfill_indices(start_date: str = "2020-01-01", *, force: bool = False) -> int:
    """Backfill NEPSE and all sector sub-indices into benchmark_index_history (and NEPSE into stock_prices)."""
    from backend.quant_pro.data_io import SECTOR_INDEX_SYMBOLS
    from backend.quant_pro.database import get_db_connection, get_db_path, init_db, save_benchmark_history
    from backend.quant_pro.vendor_api import fetch_ohlcv_chunk

    init_db()
    benchmarks = sorted(set(SECTOR_INDEX_SYMBOLS.values()))
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    total_written = 0

    conn = get_db_connection()
    try:
        coverage = {
            row[0]: (row[1], row[2], int(row[3] or 0))
            for row in conn.execute(
                "SELECT benchmark, MIN(date), MAX(date), COUNT(*) FROM benchmark_index_history GROUP BY benchmark"
            ).fetchall()
        }
        nepse_px_max = conn.execute(
            "SELECT MAX(date) FROM stock_prices WHERE symbol = 'NEPSE'"
        ).fetchone()[0]
    finally:
        conn.close()

    print(f"Backfilling {len(benchmarks)} indices ({start_date} -> {today_str}) into {get_db_path()}")
    for i, sym in enumerate(benchmarks, 1):
        min_d, max_d, cnt = coverage.get(sym, (None, None, 0))
        if not force and min_d and max_d and min_d <= start_date[:7] + "-31" and max_d >= today_str:
            print(f"[{i:2d}/{len(benchmarks)}] {sym:<20} skip (have {cnt} rows: {min_d}..{max_d})")
            continue
        if not force and min_d and max_d and min_d <= start_date[:7] + "-31":
            fetch_start = datetime.strptime(max_d[:10], "%Y-%m-%d") + timedelta(days=1)
        else:
            fetch_start = datetime.strptime(start_date, "%Y-%m-%d")

        if fetch_start.date() > today_dt.date():
            print(f"[{i:2d}/{len(benchmarks)}] {sym:<20} up-to-date ({min_d}..{max_d})")
            continue

        try:
            df = fetch_ohlcv_chunk(sym, ts(fetch_start), ts(today_dt))
            if df is None or df.empty:
                print(f"[{i:2d}/{len(benchmarks)}] {sym:<20}     0 rows (no data)")
                continue
            written = save_benchmark_history(sym, df.to_dict("records"), source="merolagani_chart")
            total_written += written
            dmin = df["Date"].min().strftime("%Y-%m-%d")
            dmax = df["Date"].max().strftime("%Y-%m-%d")
            print(f"[{i:2d}/{len(benchmarks)}] {sym:<20} {written:>5} rows ({dmin}..{dmax})")
        except Exception as e:
            print(f"[{i:2d}/{len(benchmarks)}] {sym:<20} WARN: {e}")

    # Also top up NEPSE in stock_prices past its stored max date
    if force or not nepse_px_max or str(nepse_px_max)[:10] < today_str:
        px_start = (
            datetime.strptime(str(nepse_px_max)[:10], "%Y-%m-%d") - timedelta(days=7)
            if (nepse_px_max and not force)
            else datetime.strptime(start_date, "%Y-%m-%d")
        )
        rows = backfill_symbol("NEPSE", px_start, today_dt)
        print(f"stock_prices NEPSE top-up ({px_start.date()} -> {today_dt.date()}): {rows} rows")
        total_written += rows

    print(f"Done — {total_written:,} index rows written.")
    return total_written


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import os

    parser = argparse.ArgumentParser(description="NEPSE Quant — data setup")
    parser.add_argument("--scrape", action="store_true",
                        help="Scrape fresh data from Merolagani instead of downloading")
    parser.add_argument("--indices", action="store_true",
                        help="Backfill NEPSE and all sector sub-indices into benchmark_index_history")
    parser.add_argument("--start", type=str, default="2020-01-01",
                        help="Start date YYYY-MM-DD for --indices (default: 2020-01-01)")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch indices even if already present")
    parser.add_argument("--proxy-only", action="store_true",
                        help="Route scraping through free proxies only (never direct IP)")
    parser.add_argument("--days", type=int, default=760,
                        help="Days of history to scrape (default 760 ≈ 2 yr). Only used with --scrape.")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Single symbol to scrape. Only used with --scrape.")
    args = parser.parse_args()

    if args.proxy_only:
        os.environ["NQT_PROXY_ONLY"] = "1"

    if args.indices:
        backfill_indices(start_date=args.start, force=args.force)
        return

    if args.scrape:
        scrape_db(days=args.days, symbol=args.symbol)
    else:
        ok = download_db()
        if not ok:
            print("\nFalling back to scrape...")
            scrape_db(days=760, symbol=None)

    print("\nLaunch the terminal with:  python3 -m apps.tui.dashboard_tui")


if __name__ == "__main__":
    main()
