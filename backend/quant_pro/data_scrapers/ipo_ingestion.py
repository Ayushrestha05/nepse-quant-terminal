#!/usr/bin/env python3
"""NEPSE IPO / FPO / Right Share issue & listing-date ingestion.

Scrapes:
  1. ShareSansar existing issues JSON API (``existing-issues?type=1..8``) —
     captures issue type (IPO, FPO, RIGHT, MUTUAL_FUND, IPO_LOCAL, IPO_MIGRANT),
     opening/closing/allotment dates, and official NEPSE ``listing_date``.
  2. Merolagani past IPO page (``Ipo.aspx?type=past``) — secondary backup source
     matched against known NEPSE company names / symbols.

Persists both sources into ``ipo_listings`` in ``data/nepse_market_data.db`` and
prints a comparison report against the ``stock_prices`` first-trading-day proxy.

Usage:
    python3 -m backend.quant_pro.data_scrapers.ipo_ingestion --proxy-only
    python3 -m backend.quant_pro.data_scrapers.ipo_ingestion --compare
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from backend.quant_pro.data_scrapers.proxy_pool import get_proxy_pool, is_proxy_only, parse_proxy_env
from backend.quant_pro.database import get_db_connection, get_db_path, init_db
from backend.quant_pro.ingest_cache import has_rows

logger = logging.getLogger(__name__)

SHARESANSAR_ISSUE_TYPES: Dict[int, str] = {
    1: "IPO",
    2: "FPO",
    3: "RIGHT",
    4: "MUTUAL_FUND",
    5: "IPO_LOCAL",
    8: "IPO_MIGRANT",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def ensure_ipo_table(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if conn is None:
        conn = get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_listings (
                symbol TEXT NOT NULL,
                company_name TEXT,
                issue_type TEXT NOT NULL,
                source TEXT NOT NULL,
                opening_date TEXT,
                closing_date TEXT,
                final_date TEXT,
                listing_date TEXT,
                total_units REAL,
                issue_price REAL,
                issue_manager TEXT,
                scraped_at_utc TEXT NOT NULL,
                PRIMARY KEY (symbol, issue_type, source)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ipo_listings_type_date ON ipo_listings(issue_type, listing_date)"
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def _strip_html(val: Any) -> str:
    if val is None:
        return ""
    return unescape(re.sub(r"<[^>]+>", "", str(val))).strip()


def _clean_date(val: Any) -> Optional[str]:
    s = _strip_html(val)
    if not s or s.lower() in {"null", "none", "n/a", "-", "0000-00-00"}:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def _clean_float(val: Any) -> Optional[float]:
    s = _strip_html(val).replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _http_get(url: str, *, params: Optional[dict] = None, headers: Optional[dict] = None, timeout: float = 20.0):
    hdrs = {"User-Agent": UA, **(headers or {})}
    if is_proxy_only() or parse_proxy_env():
        pool = get_proxy_pool()
        return pool.get(url, params=params, headers=hdrs, timeout=timeout)
    import requests
    return requests.get(url, params=params, headers=hdrs, timeout=timeout, verify=True)


def scrape_sharesansar_issues(issue_types: Optional[Dict[int, str]] = None) -> List[Dict[str, Any]]:
    """Fetch ShareSansar's paginated DataTables JSON for IPO, FPO, Right, Mutual Fund."""
    types = issue_types or SHARESANSAR_ISSUE_TYPES
    url = "https://www.sharesansar.com/existing-issues"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": url,
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records: List[Dict[str, Any]] = []

    for type_id, label in types.items():
        start = 0
        page_size = 50
        while True:
            resp = _http_get(
                url,
                params={"type": type_id, "draw": 1, "start": start, "length": page_size},
                headers=headers,
                timeout=25.0,
            )
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("data") or []
            if not rows:
                break
            for item in rows:
                comp = item.get("company") or {}
                sym = _strip_html(comp.get("symbol") or item.get("symbol")).upper()
                name = _strip_html(comp.get("companyname") or item.get("companyname"))
                if not sym:
                    continue
                records.append(
                    {
                        "symbol": sym,
                        "company_name": name,
                        "issue_type": label,
                        "source": "sharesansar",
                        "opening_date": _clean_date(item.get("opening_date")),
                        "closing_date": _clean_date(item.get("closing_date")),
                        "final_date": _clean_date(item.get("final_date")),
                        "listing_date": _clean_date(item.get("listing_date")),
                        "total_units": _clean_float(item.get("total_units")),
                        "issue_price": _clean_float(item.get("issue_price")),
                        "issue_manager": _strip_html(item.get("issue_manager")),
                        "scraped_at_utc": now_utc,
                    }
                )
            total = int(payload.get("recordsTotal") or 0)
            start += len(rows)
            if start >= total or len(rows) < page_size:
                break
        logger.info("ShareSansar %s (type=%d): collected cumulative %d records", label, type_id, len(records))

    return records


def scrape_merolagani_past_ipos(db_path: str | Path | None = None) -> List[Dict[str, Any]]:
    """Scrape Merolagani's past IPO announcements and map company names to DB symbols."""
    from backend.quant_pro.data_scrapers.sentiment_ingestion import _load_name_to_symbol, map_names_to_tickers

    db = str(db_path or get_db_path())
    name_map = _load_name_to_symbol(db)
    resp = _http_get("https://merolagani.com/Ipo.aspx?type=past", timeout=25.0)
    resp.raise_for_status()
    html = resp.content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    records: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for a in soup.find_all("a", href=re.compile(r"AnnouncementDetail\.aspx\?id=\d+", re.I)):
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if not text or len(text) < 12:
            continue
        upper = text.upper()
        if "FPO" in upper:
            issue_type = "FPO"
        elif "RIGHT" in upper:
            issue_type = "RIGHT"
        elif "MUTUAL FUND" in upper:
            issue_type = "MUTUAL_FUND"
        elif "IPO" in upper:
            issue_type = "IPO"
        else:
            continue

        # Try explicit ticker in parens first, e.g. "(NABIL)", else company name map
        sym = ""
        m_par = re.search(r"\(([A-Z]{2,10})\)", upper)
        if m_par:
            sym = m_par.group(1)
        else:
            hits = map_names_to_tickers(text, name_map)
            if hits:
                sym = hits[0]
        if not sym or (sym, issue_type) in seen:
            continue
        seen.add((sym, issue_type))

        # Best-effort ISO date if present in text
        ad_date = _clean_date(text)
        records.append(
            {
                "symbol": sym,
                "company_name": text[:140],
                "issue_type": issue_type,
                "source": "merolagani",
                "opening_date": ad_date,
                "closing_date": None,
                "final_date": None,
                "listing_date": None,
                "total_units": None,
                "issue_price": None,
                "issue_manager": None,
                "scraped_at_utc": now_utc,
            }
        )
    logger.info("Merolagani past IPO page: matched %d symbol records", len(records))
    return records


def save_ipo_listings(records: List[Dict[str, Any]], conn: sqlite3.Connection | None = None) -> int:
    if not records:
        return 0
    own = conn is None
    if conn is None:
        conn = get_db_connection()
    try:
        ensure_ipo_table(conn)
        conn.executemany(
            """
            INSERT OR REPLACE INTO ipo_listings (
                symbol, company_name, issue_type, source,
                opening_date, closing_date, final_date, listing_date,
                total_units, issue_price, issue_manager, scraped_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r["symbol"],
                    r.get("company_name"),
                    r["issue_type"],
                    r["source"],
                    r.get("opening_date"),
                    r.get("closing_date"),
                    r.get("final_date"),
                    r.get("listing_date"),
                    r.get("total_units"),
                    r.get("issue_price"),
                    r.get("issue_manager"),
                    r["scraped_at_utc"],
                )
                for r in records
            ],
        )
        conn.commit()
        return len(records)
    finally:
        if own:
            conn.close()


def load_ipo_listing_map(db_path: str | Path | None = None) -> Dict[str, Dict[str, Any]]:
    """Load confirmed IPO symbols -> metadata (preferring ShareSansar with listing_date)."""
    db = str(db_path or get_db_path())
    try:
        conn = sqlite3.connect(db, timeout=30)
        rows = conn.execute(
            """
            SELECT symbol, issue_type, source, opening_date, closing_date, listing_date
            FROM ipo_listings
            WHERE issue_type IN ('IPO', 'FPO', 'MUTUAL_FUND', 'RIGHT')
            """
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for sym, itype, src, odate, cdate, ldate in rows:
        sym_u = str(sym).upper().strip()
        cur = out.get(sym_u)
        # Prefer IPO over non-IPO, and sharesansar with listing_date over merolagani
        if cur is None or (itype == "IPO" and cur["issue_type"] != "IPO") or (
            itype == cur["issue_type"] and ldate and not cur.get("listing_date")
        ):
            out[sym_u] = {
                "issue_type": itype,
                "source": src,
                "opening_date": odate,
                "closing_date": cdate,
                "listing_date": ldate,
            }
    return out


def build_ipo_comparison_report(db_path: str | Path | None = None) -> str:
    """Compare ShareSansar/Merolagani IPO records vs stock_prices first-trading-day proxy."""
    db = str(db_path or get_db_path())
    conn = sqlite3.connect(db, timeout=30)
    try:
        ensure_ipo_table(conn)
        px_first = {
            str(sym).upper(): str(d)[:10]
            for sym, d in conn.execute(
                "SELECT symbol, MIN(date) FROM stock_prices GROUP BY symbol"
            ).fetchall()
        }
        ss_rows = conn.execute(
            """
            SELECT symbol, issue_type, opening_date, closing_date, listing_date
            FROM ipo_listings WHERE source = 'sharesansar'
            """
        ).fetchall()
        ml_syms = {
            (str(s).upper(), str(t))
            for s, t in conn.execute(
                "SELECT symbol, issue_type FROM ipo_listings WHERE source = 'merolagani'"
            ).fetchall()
        }
    finally:
        conn.close()

    by_type: Dict[str, set[str]] = {}
    ss_ipo_dates: Dict[str, Optional[str]] = {}
    for sym, itype, _od, _cd, ldate in ss_rows:
        s = str(sym).upper()
        by_type.setdefault(itype, set()).add(s)
        if itype == "IPO":
            ss_ipo_dates[s] = ldate

    proxy_post2017 = {
        s: d for s, d in px_first.items()
        if d >= "2018-01-01" and s != "NEPSE" and not s.startswith("SECTOR::")
    }
    confirmed_ipos = by_type.get("IPO", set())
    non_ipo_in_proxy = {
        s: t
        for t in ("FPO", "MUTUAL_FUND", "RIGHT")
        for s in (by_type.get(t, set()) & set(proxy_post2017))
        if s not in confirmed_ipos
    }

    deltas: List[Tuple[str, str, str, int]] = []
    for sym, ldate in ss_ipo_dates.items():
        if ldate and sym in px_first:
            d_list = datetime.strptime(ldate, "%Y-%m-%d").date()
            d_px = datetime.strptime(px_first[sym], "%Y-%m-%d").date()
            deltas.append((sym, ldate, px_first[sym], (d_px - d_list).days))

    within_7d = sum(1 for _, _, _, d in deltas if abs(d) <= 7)
    within_30d = sum(1 for _, _, _, d in deltas if abs(d) <= 30)
    median_delta = sorted(d for _, _, _, d in deltas)[len(deltas) // 2] if deltas else 0

    lines = [
        "IPO LISTING COMPARISON REPORT (ShareSansar + Merolagani vs first-trading-day proxy)",
        f"  ShareSansar records by type: { {k: len(v) for k, v in sorted(by_type.items())} }",
        f"  Merolagani backup records:   {len(ml_syms)}",
        f"  Post-2017 stock_prices proxy universe: {len(proxy_post2017)} symbols",
        f"  Overlap proxy ∩ ShareSansar IPO:       {len(set(proxy_post2017) & confirmed_ipos)} symbols",
        f"  Non-IPOs caught in proxy (FPO/MF/etc): {len(non_ipo_in_proxy)} symbols",
        f"  IPOs with official listing_date & prices: {len(deltas)}",
        f"  |first_px - listing_date| <= 7d:  {within_7d}/{len(deltas)}  |  <= 30d: {within_30d}/{len(deltas)}  |  median delta: {median_delta:+d}d",
    ]
    if deltas:
        outliers = sorted(deltas, key=lambda x: abs(x[3]), reverse=True)[:10]
        lines.append("  Largest listing_date vs first_trading_day deltas:")
        for sym, ldate, pdate, delta in outliers:
            lines.append(f"    {sym:<10} official={ldate}  first_px={pdate}  delta={delta:+d}d")
    return "\n".join(lines)


def run_ipo_ingestion(*, force: bool = False, db_path: str | Path | None = None) -> int:
    init_db()
    db = str(db_path or get_db_path())
    ensure_ipo_table()

    total = 0
    if force or not has_rows(db, "SELECT COUNT(*) FROM ipo_listings WHERE source = 'sharesansar'"):
        ss_recs = scrape_sharesansar_issues()
        total += save_ipo_listings(ss_recs)
    else:
        logger.info("Skip ShareSansar IPO scrape — ipo_listings already populated (pass --force to refresh)")

    if force or not has_rows(db, "SELECT COUNT(*) FROM ipo_listings WHERE source = 'merolagani'"):
        try:
            ml_recs = scrape_merolagani_past_ipos(db)
            total += save_ipo_listings(ml_recs)
        except Exception as exc:
            logger.warning("Merolagani IPO backup scrape failed: %s", exc)
    else:
        logger.info("Skip Merolagani IPO scrape — ipo_listings already populated")

    return total


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Scrape NEPSE IPO/FPO issue & listing dates.")
    parser.add_argument("--force", action="store_true", help="Re-scrape even if ipo_listings already has rows.")
    parser.add_argument("--compare", action="store_true", help="Print comparison report only (no scraping).")
    parser.add_argument("--proxy-only", action="store_true", help="Route all scraping via free proxies only.")
    args = parser.parse_args()

    if args.proxy_only:
        os.environ["NQT_PROXY_ONLY"] = "1"

    if not args.compare:
        written = run_ipo_ingestion(force=args.force)
        print(f"Saved {written} IPO/issue records into ipo_listings.")

    print()
    print(build_ipo_comparison_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
