#!/usr/bin/env python3
"""NEPSE floorsheet / broker-flow ingestion CLI.

Examples:
    python3 -m backend.quant_pro.data_scrapers.floorsheet_ingestion --create-tables
    python3 -m backend.quant_pro.data_scrapers.floorsheet_ingestion --summary
    python3 -m backend.quant_pro.data_scrapers.floorsheet_ingestion --symbols NABIL NICA --start 2026-05-01 --end 2026-05-27
    python3 -m backend.quant_pro.data_scrapers.floorsheet_ingestion --all --date-level
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import date, timedelta

from backend.quant_pro.paths import get_project_root

project_root = str(get_project_root(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.quant_pro.database import get_db_connection, init_db  # noqa: E402
from backend.quant_pro.floorsheet_scraper import (  # noqa: E402
    ensure_floorsheet_tables,
    get_raw_floorsheet_connection,
    get_raw_floorsheet_db_path,
    scrape_all,
)

LOG = logging.getLogger(__name__)

DEFAULT_SYMBOLS = [
    "NABIL",
    "NICA",
    "GBIME",
    "KBL",
    "SBI",
    "EBL",
    "NMB",
    "SANIMA",
    "NBL",
    "ADBL",
    "NLIC",
    "LICN",
    "SHIVM",
    "NTC",
    "NRIC",
    "CHDC",
    "UPPER",
    "HIDCL",
    "API",
    "AKPL",
]


def _all_symbols_from_db() -> list[str]:
    try:
        conn = get_db_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT symbol
            FROM stock_prices
            WHERE symbol != 'NEPSE'
              AND symbol NOT LIKE 'SECTOR::%'
            ORDER BY symbol
            """
        ).fetchall()
        conn.close()
        return [str(row[0]).upper() for row in rows if str(row[0] or "").strip()]
    except sqlite3.Error as exc:
        LOG.warning("Could not load symbols from DB: %s", exc)
        return []


def show_summary() -> None:
    conn = get_db_connection()
    try:
        ensure_floorsheet_tables(conn)
        signal_rows = conn.execute("SELECT COUNT(*) FROM broker_signals_v2").fetchone()[0]
        micro_rows = conn.execute("SELECT COUNT(*) FROM broker_microstructure").fetchone()[0]
        logged_days = conn.execute("SELECT COUNT(*) FROM floorsheet_scrape_log").fetchone()[0]
        agg_min, agg_max = conn.execute("SELECT MIN(as_of_date), MAX(as_of_date) FROM broker_signals_v2").fetchone()
        top_rows = conn.execute(
            """
            SELECT symbol, as_of_date, smart_money_score, circular_score, pump_score, n_trades
            FROM broker_signals_v2
            ORDER BY as_of_date DESC, smart_money_score DESC, circular_score DESC, pump_score DESC
            LIMIT 10
            """
        ).fetchall()
    finally:
        conn.close()

    raw_path = get_raw_floorsheet_db_path()
    total_trades, n_symbols, n_dates, min_date, max_date = 0, 0, 0, None, None
    if raw_path.exists():
        rconn = get_raw_floorsheet_connection(raw_path)
        try:
            total_trades, n_symbols, n_dates = rconn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT symbol), COUNT(DISTINCT as_of_date) FROM floorsheet_trades"
            ).fetchone()
            min_date, max_date = rconn.execute(
                "SELECT MIN(as_of_date), MAX(as_of_date) FROM floorsheet_trades"
            ).fetchone()
        finally:
            rconn.close()

    print("FLOORSHEET / BROKER-FLOW SUMMARY")
    print(f"  Raw DB:           {raw_path}")
    print(f"  Raw trades:       {int(total_trades or 0):,}")
    print(f"  Symbols covered:  {int(n_symbols or 0):,}")
    print(f"  Trading days:     {int(n_dates or 0):,} (logged: {int(logged_days or 0):,})")
    print(f"  Date range:       {min_date or agg_min or 'N/A'} -> {max_date or agg_max or 'N/A'}")
    print(f"  Broker signals:   {int(signal_rows or 0):,} (microstructure: {int(micro_rows or 0):,})")
    if top_rows:
        print()
        print("  Latest broker signals:")
        for sym, day, smart, circ, pump, trades in top_rows:
            print(f"    {day} {sym:<8} smart={smart or 0:.3f} circ={circ or 0:.3f} pump={pump or 0:.3f} trades={trades or 0}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Scrape NEPSE floorsheet data and broker-flow signals.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Ticker symbols to scrape. Defaults to liquid symbols.")
    parser.add_argument("--all", action="store_true", help="Scrape all symbols found in stock_prices.")
    parser.add_argument("--date-level", action="store_true", help="Fetch the full market per date instead of per symbol.")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD. Default is 7 days ago.")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD. Default is today.")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent HTTP workers. Default: 4.")
    parser.add_argument("--rps", type=float, default=1.0, help="Approximate request rate per worker batch. Default: 1.0.")
    parser.add_argument("--proxy-only", action="store_true", help="Route all scraping via free proxies only (never direct IP).")
    parser.add_argument("--raw-db", default=None, help="Path to separate SQLite DB for raw floorsheet_trades.")
    parser.add_argument("--no-skip", action="store_true", help="Fetch even when symbol/date data already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse without writing rows.")
    parser.add_argument("--summary", action="store_true", help="Show current DB summary and exit.")
    parser.add_argument("--create-tables", action="store_true", help="Create floorsheet tables and exit.")
    args = parser.parse_args()

    if args.proxy_only:
        os.environ["NQT_PROXY_ONLY"] = "1"
    if args.raw_db:
        os.environ["NEPSE_FLOORSHEET_RAW_DB"] = args.raw_db

    init_db()
    ensure_floorsheet_tables()

    if args.create_tables:
        print("Floorsheet tables created or already present.")
        return
    if args.summary:
        show_summary()
        return

    end_date = date.fromisoformat(args.end) if args.end else date.today()
    start_date = date.fromisoformat(args.start) if args.start else end_date - timedelta(days=7)
    if args.all:
        symbols = _all_symbols_from_db() or DEFAULT_SYMBOLS
    elif args.symbols:
        symbols = [item.upper() for item in args.symbols]
    else:
        symbols = DEFAULT_SYMBOLS

    print("Floorsheet ingestion")
    print(f"  Symbols:    {len(symbols):,}")
    print(f"  Date range: {start_date} -> {end_date}")
    print(f"  Mode:       {'date-level' if args.date_level else 'symbol-level'}")
    print(f"  Proxy-only: {args.proxy_only}")
    print(f"  Raw DB:     {get_raw_floorsheet_db_path(args.raw_db)}")
    print(f"  Dry run:    {args.dry_run}")

    stats = scrape_all(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        max_workers=args.workers,
        rps=args.rps,
        skip_existing=not args.no_skip,
        dry_run=args.dry_run,
        mark_complete=args.date_level or args.all,
        raw_db_path=args.raw_db,
    )

    print()
    print("Scraping complete")
    print(f"  Total pairs: {stats.get('total_pairs', 0):,}")
    print(f"  Skipped:     {stats.get('skipped', 0):,}")
    print(f"  Fetched:     {stats.get('fetched', 0):,}")
    print(f"  Inserted:    {stats.get('inserted', 0):,}")
    print(f"  Errors:      {stats.get('errors', 0):,}")
    if not args.dry_run:
        print()
        show_summary()


if __name__ == "__main__":
    main()
