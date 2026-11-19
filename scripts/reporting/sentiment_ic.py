#!/usr/bin/env python3
"""Daily rank IC of sentiment_scores vs next-day returns.

Usage:
    python3 -m scripts.reporting.sentiment_ic
    python3 -m scripts.reporting.sentiment_ic --db data/nepse_market_data.db --days 120

Prints mean Spearman IC and directional hit rate. If IC ≈ 0, do not weight the signal.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backend.quant_pro.database import get_db_path


def _load_sentiment(conn: sqlite3.Connection, days: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT date, symbol, score, n_documents
        FROM sentiment_scores
        WHERE symbol IS NOT NULL
          AND date >= date('now', ?)
        """,
        conn,
        params=[f"-{int(days)} day"],
    )


def _load_returns(conn: sqlite3.Connection, days: int) -> pd.DataFrame:
    # Prefer stock_prices if present; fall back to market_quotes daily closes if needed.
    try:
        prices = pd.read_sql_query(
            """
            SELECT date, symbol, close
            FROM stock_prices
            WHERE symbol NOT LIKE 'SECTOR::%'
              AND symbol != 'NEPSE'
              AND date >= date('now', ?)
            ORDER BY symbol, date
            """,
            conn,
            params=[f"-{int(days) + 5} day"],
        )
    except Exception:
        return pd.DataFrame()

    if prices.empty:
        return prices
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values(["symbol", "date"])
    prices["next_ret"] = prices.groupby("symbol")["close"].pct_change().shift(-1)
    return prices.dropna(subset=["next_ret"])


def spearman_ic(scores: pd.Series, rets: pd.Series) -> float:
    if len(scores) < 3:
        return float("nan")
    return float(scores.corr(rets, method="spearman"))


def compute_ic(sentiment: pd.DataFrame, returns: pd.DataFrame) -> dict:
    if sentiment.empty or returns.empty:
        return {"n_days": 0, "mean_ic": float("nan"), "hit_rate": float("nan"), "n_pairs": 0}

    sentiment = sentiment.copy()
    sentiment["date"] = pd.to_datetime(sentiment["date"])
    # One score per symbol-day (mean across sources/models)
    daily = (
        sentiment.groupby(["date", "symbol"], as_index=False)
        .agg(score=("score", "mean"), n_documents=("n_documents", "sum"))
    )

    merged = daily.merge(
        returns[["date", "symbol", "next_ret"]],
        on=["date", "symbol"],
        how="inner",
    )
    if merged.empty:
        return {"n_days": 0, "mean_ic": float("nan"), "hit_rate": float("nan"), "n_pairs": 0}

    ics = []
    for _, group in merged.groupby("date"):
        if len(group) < 3:
            continue
        ics.append(spearman_ic(group["score"], group["next_ret"]))

    ics = [x for x in ics if x == x]  # drop NaN
    same_sign = ((merged["score"] > 0) & (merged["next_ret"] > 0)) | (
        (merged["score"] < 0) & (merged["next_ret"] < 0)
    )
    decided = merged["score"] != 0
    hit_rate = float(same_sign[decided].mean()) if decided.any() else float("nan")

    return {
        "n_days": len(ics),
        "mean_ic": float(np.mean(ics)) if ics else float("nan"),
        "hit_rate": hit_rate,
        "n_pairs": int(len(merged)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sentiment vs next-day return IC")
    parser.add_argument("--db", default=str(get_db_path()))
    parser.add_argument("--days", type=int, default=120)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        sentiment = _load_sentiment(conn, args.days)
        returns = _load_returns(conn, args.days)
    finally:
        conn.close()

    stats = compute_ic(sentiment, returns)
    print(
        f"sentiment IC ({args.days}d): mean_ic={stats['mean_ic']:.4f} "
        f"hit_rate={stats['hit_rate']:.4f} n_days={stats['n_days']} n_pairs={stats['n_pairs']}"
    )
    if stats["n_days"] == 0:
        print("No overlapping sentiment/return rows. Ingest news first, then rerun.")
        return 1
    if abs(stats["mean_ic"]) < 0.02:
        print("IC ≈ 0 — do not add weight to NLP_SENTIMENT until the signal improves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
