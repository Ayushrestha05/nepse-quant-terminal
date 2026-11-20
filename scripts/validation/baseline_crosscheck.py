"""Cross-check local stock_prices closes vs menaceXnadin adjusted CSVs."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
from urllib.request import urlopen, Request

import pandas as pd

MENACE_RAW = (
    "https://raw.githubusercontent.com/menaceXnadin/"
    "nepse-historical-market-data-csv/master/data"
)
CLOSE_TOL = 0.01  # 1% relative
EXCLUDE_SHARE = 0.05  # exclude if >5% of overlapping days exceed CLOSE_TOL


def mismatch_share(
    ours: pd.Series,
    theirs: pd.Series,
    *,
    tol: float = CLOSE_TOL,
) -> float:
    """Fraction of overlapping dates where |ours/theirs - 1| > tol."""
    aligned = pd.concat([ours.rename("ours"), theirs.rename("theirs")], axis=1).dropna()
    if aligned.empty:
        return float("nan")
    rel = (aligned["ours"] / aligned["theirs"] - 1.0).abs()
    return float((rel > tol).mean())


def should_exclude(share: float, *, threshold: float = EXCLUDE_SHARE) -> bool:
    if share != share:  # NaN
        return False
    return share > threshold


def _symbol_path_token(symbol: str) -> str:
    return str(symbol).upper().replace("/", "_")


def menace_url(symbol: str, *, kind: str = "stock") -> str:
    token = _symbol_path_token(symbol)
    if kind == "index" or symbol.upper() == "NEPSE":
        return f"{MENACE_RAW}/index/adjusted/{token}_adjusted.csv"
    return f"{MENACE_RAW}/stock/adjusted/{token}_adjusted.csv"


def fetch_menace_adjusted(
    symbol: str,
    cache_dir: Path,
    *,
    kind: str = "stock",
    force: bool = False,
) -> pd.DataFrame:
    """Return DataFrame indexed by date with column close. Caches under cache_dir."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    token = _symbol_path_token(symbol)
    path = cache_dir / f"{token}_adjusted.csv"
    if force or not path.exists():
        url = menace_url(symbol, kind=kind)
        req = Request(url, headers={"User-Agent": "nqt-baseline-crosscheck/1.0"})
        with urlopen(req, timeout=60) as resp:
            path.write_bytes(resp.read())
    df = pd.read_csv(path)
    # menace schema: time,symbol,open,close,high,low,volume,category
    date_col = "time" if "time" in df.columns else "date"
    df[date_col] = pd.to_datetime(df[date_col])
    out = df.set_index(date_col)[["close"]].sort_index()
    out.index = out.index.normalize()
    return out


def local_closes(conn, symbol: str, start: str, end: str) -> pd.Series:
    df = pd.read_sql_query(
        """
        SELECT date, close FROM stock_prices
        WHERE symbol = ? AND date >= ? AND date <= ?
        ORDER BY date
        """,
        conn,
        params=(symbol, start, end),
        parse_dates=["date"],
    )
    if df.empty:
        return pd.Series(dtype=float)
    s = df.set_index("date")["close"].sort_index()
    s.index = s.index.normalize()
    return s


def pick_liquid_symbols(conn, start: str, end: str, n: int = 20) -> list[str]:
    df = pd.read_sql_query(
        """
        SELECT symbol, SUM(COALESCE(volume, 0) * COALESCE(close, 0)) AS turnover
        FROM stock_prices
        WHERE date >= ? AND date <= ?
          AND symbol NOT LIKE 'SECTOR::%'
          AND symbol != 'NEPSE'
        GROUP BY symbol
        ORDER BY turnover DESC
        LIMIT ?
        """,
        conn,
        params=(start, end, n),
    )
    return [str(s) for s in df["symbol"].tolist()]


def crosscheck_symbols(
    conn,
    symbols: Iterable[str],
    *,
    start: str,
    end: str,
    cache_dir: Path,
    force_download: bool = False,
) -> list[dict]:
    rows = []
    for symbol in symbols:
        kind = "index" if symbol.upper() == "NEPSE" else "stock"
        try:
            theirs = fetch_menace_adjusted(symbol, cache_dir, kind=kind, force=force_download)["close"]
        except Exception as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "overlap_days": 0,
                    "mismatch_share": float("nan"),
                    "exclude": False,
                    "error": str(exc),
                }
            )
            continue
        ours = local_closes(conn, symbol, start, end)
        aligned = pd.concat([ours.rename("o"), theirs.rename("t")], axis=1).dropna()
        share = mismatch_share(ours, theirs)
        rows.append(
            {
                "symbol": symbol,
                "overlap_days": int(len(aligned)),
                "mismatch_share": None if share != share else round(share, 4),
                "exclude": should_exclude(share),
                "error": "",
            }
        )
    return rows
