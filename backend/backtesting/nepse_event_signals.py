"""Nepal-specific alpha signal generators for NEPSE walk-forward backtesting.

All generators follow the `simple_backtest.py` contract and enforce strict
causality (only prices/events available on or before `date` are inspected).

Signal families implemented here:
1. book_closure_runup   - Pre-bookclose dividend/bonus run-up (statutory 3-15d notice window)
2. ex_date_gap          - Post-ex-date bonus/rights adjustment rebound
3. circuit_continuation - Upper-circuit (+8.5%+) high-volume breakout continuation
4. ipo_momentum         - Post-IPO listing discovery momentum (excludes mergers)
5. sector_rotation      - Equal-weighted synthetic sector index rotation
6. earnings_drift       - Post-earnings announcement drift (quarterly_earnings)
7. calendar_festival    - Dashain/Tihar & Ashad fiscal year-end liquidity effects
8. nrb_policy           - Post-NRB Monetary Policy BFI follow-through
9. lead_lag             - Intra-sector bellwether-to-laggard catch-up
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from backend.quant_pro.alpha_practical import AlphaSignal, SignalType
from backend.quant_pro.nepal_calendar import (
    NRB_POLICY_DATES,
    ashad_end_dates,
    festival_windows,
)
from backend.quant_pro.sectors import SECTOR_GROUPS
from backend.quant_pro.signal_ranking import is_tradeable_signal_symbol

logger = logging.getLogger(__name__)

# BFI sectors most directly impacted by NRB Monetary Policy
_BFI_SECTORS = {"Commercial Banks", "Development Banks", "Finance", "Microfinance"}
_FESTIVAL_SECTORS = {"Commercial Banks", "Hydropower", "Life Insurance", "Microfinance"}

# Reverse map: symbol -> sector
_SYMBOL_TO_SECTOR: Dict[str, str] = {
    sym: sector for sector, syms in SECTOR_GROUPS.items() for sym in syms
}


def _symbol_sector(symbol: str) -> Optional[str]:
    return _SYMBOL_TO_SECTOR.get(symbol)


def _history_slice(
    prices_df: pd.DataFrame,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]],
    symbol: str,
    target_date: datetime,
    tail: Optional[int] = None,
) -> Optional[pd.DataFrame]:
    """Return sorted rows for `symbol` with `date <= target_date`."""
    ts = pd.Timestamp(target_date)
    if symbol_cache is not None:
        cached = symbol_cache.get(symbol)
        if cached is None:
            return None
        frame, dates = cached
        end_idx = int(np.searchsorted(dates, np.datetime64(ts), side="right"))
        if end_idx <= 0:
            return None
        start_idx = max(0, end_idx - tail) if tail is not None else 0
        return frame.iloc[start_idx:end_idx]
    sub = prices_df[(prices_df["symbol"] == symbol) & (prices_df["date"] <= ts)].sort_values("date")
    if sub.empty:
        return None
    return sub.tail(tail) if tail is not None else sub


def _is_fresh_row(hist: pd.DataFrame, target_date: datetime, max_stale_days: int = 5) -> bool:
    last_dt = pd.Timestamp(hist.iloc[-1]["date"])
    return (pd.Timestamp(target_date) - last_dt).days <= max_stale_days


# =============================================================================
# PRECOMPUTATION LOADERS (CALLED ONCE PER BACKTEST)
# =============================================================================

def load_merger_symbols(conn: sqlite3.Connection) -> Set[str]:
    """Return symbols whose corporate_actions mention a merger or acquisition."""
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT symbol FROM corporate_actions
            WHERE lower(coalesce(agenda, '') || ' ' || coalesce(description, '')) LIKE '%merg%'
               OR lower(coalesce(agenda, '') || ' ' || coalesce(description, '')) LIKE '%acqui%'
            """
        ).fetchall()
        return {str(r[0]).upper().strip() for r in rows if r and r[0]}
    except Exception as exc:
        logger.warning("Could not load merger symbols: %s", exc)
        return set()


def load_quarterly_earnings_df(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load quarterly_earnings with announcement_date for strictly causal PEAD signals."""
    try:
        df = pd.read_sql_query(
            """
            SELECT symbol, fiscal_year, quarter, eps, net_profit, announcement_date
            FROM quarterly_earnings
            WHERE announcement_date IS NOT NULL
            ORDER BY symbol, announcement_date
            """,
            conn,
        )
        if df.empty:
            return df
        df["announcement_date"] = pd.to_datetime(df["announcement_date"], errors="coerce")
        df = df.dropna(subset=["announcement_date"]).copy()
        df["net_profit"] = pd.to_numeric(df["net_profit"], errors="coerce")
        df["eps"] = pd.to_numeric(df["eps"], errors="coerce")
        df["quarter"] = pd.to_numeric(df["quarter"], errors="coerce")
        # Deduplicate multiple rows for same (symbol, fiscal_year, quarter) keeping earliest announcement
        df = df.sort_values("announcement_date").drop_duplicates(
            subset=["symbol", "fiscal_year", "quarter"], keep="first"
        )
        return df.reset_index(drop=True)
    except Exception as exc:
        logger.warning("Could not load quarterly_earnings: %s", exc)
        return pd.DataFrame()


def build_synthetic_sector_indices(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Build equal-weighted cumulative sector indices causally from stock_prices.

    Returns a DataFrame indexed by trading date with one column per sector.
    Each day's sector return is the cross-sectional mean daily return of active
    constituent stocks (capped to +-12% to guard against unadjusted splits).
    """
    if prices_df.empty:
        return pd.DataFrame()
    work = prices_df[["symbol", "date", "close"]].copy()
    work["sector"] = work["symbol"].map(_SYMBOL_TO_SECTOR)
    work = work.dropna(subset=["sector"])
    if work.empty:
        return pd.DataFrame()

    pivot = work.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    daily_rets = pivot.pct_change(fill_method=None).clip(-0.12, 0.12)

    sector_cols: Dict[str, pd.Series] = {}
    for sector, syms in SECTOR_GROUPS.items():
        present = [s for s in syms if s in daily_rets.columns]
        if len(present) < 3:
            continue
        sec_ret = daily_rets[present].mean(axis=1, skipna=True).fillna(0.0)
        sector_cols[sector] = (1.0 + sec_ret).cumprod()
    if not sector_cols:
        return pd.DataFrame()
    return pd.DataFrame(sector_cols, index=pivot.index)


# =============================================================================
# 1. BOOK-CLOSURE RUN-UP
# =============================================================================

def generate_book_closure_runup_signals_at_date(
    prices_df: pd.DataFrame,
    corp_actions_df: Optional[pd.DataFrame],
    date: datetime,
    *,
    min_days_before: int = 3,
    max_days_before: int = 15,
    min_total_payout_pct: float = 10.0,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Buy dividend/bonus stocks during the statutory 3-15d pre-bookclose run-up."""
    if corp_actions_df is None or corp_actions_df.empty:
        return []
    ts = pd.Timestamp(date)
    win_start = ts + timedelta(days=min_days_before)
    win_end = ts + timedelta(days=max_days_before)

    upcoming = corp_actions_df[
        (corp_actions_df["bookclose_date"] >= win_start)
        & (corp_actions_df["bookclose_date"] <= win_end)
    ]
    if upcoming.empty:
        return []

    signals: List[AlphaSignal] = []
    seen: Set[str] = set()
    for _, row in upcoming.iterrows():
        symbol = str(row["symbol"]).upper().strip()
        if symbol in seen or not is_tradeable_signal_symbol(symbol):
            continue
        cash_div = float(row.get("cash_dividend_pct") or 0.0)
        bonus = float(row.get("bonus_share_pct") or 0.0)
        total_payout = cash_div + bonus
        if total_payout < min_total_payout_pct:
            continue

        hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=25)
        if hist is None or len(hist) < 10 or not _is_fresh_row(hist, ts):
            continue
        closes = hist["close"].to_numpy(dtype=float)
        if closes[-1] <= 0 or closes[-10] <= 0:
            continue
        ret_10d = closes[-1] / closes[-10] - 1.0
        if ret_10d < -0.15:
            continue
        turnover = float((hist["close"].tail(5) * hist["volume"].tail(5)).mean())
        if turnover < 100_000:
            continue

        # Bonus shares carry stronger retail demand in NEPSE than cash alone
        eff_yield = bonus * 1.2 + cash_div * 0.8
        strength = min(1.0, 0.35 + eff_yield / 50.0)
        bookclose_ts = pd.Timestamp(row["bookclose_date"])
        seen.add(symbol)
        signals.append(
            AlphaSignal(
                symbol=symbol,
                signal_type=SignalType.BOOK_CLOSURE_RUNUP,
                direction=1,
                strength=float(strength),
                confidence=0.72,
                reasoning=(
                    f"Bookclose {bookclose_ts.strftime('%Y-%m-%d')} "
                    f"({(bookclose_ts - ts).days}d): bonus {bonus:.1f}% + cash {cash_div:.1f}%"
                ),
                target_exit_date=(bookclose_ts - timedelta(days=1)).to_pydatetime(),
            )
        )
    return signals


# =============================================================================
# 2. EX-DATE GAP REBOUND (BONUS / RIGHTS)
# =============================================================================

def generate_ex_date_gap_signals_at_date(
    prices_df: pd.DataFrame,
    corp_actions_df: Optional[pd.DataFrame],
    date: datetime,
    *,
    max_days_after: int = 10,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Buy bonus/right-share stocks rebounding right after bookclose price adjustment."""
    if corp_actions_df is None or corp_actions_df.empty:
        return []
    ts = pd.Timestamp(date)
    win_start = ts - timedelta(days=max_days_after)

    recent = corp_actions_df[
        (corp_actions_df["bookclose_date"] >= win_start)
        & (corp_actions_df["bookclose_date"] <= ts)
    ]
    if recent.empty:
        return []

    signals: List[AlphaSignal] = []
    seen: Set[str] = set()
    for _, row in recent.iterrows():
        symbol = str(row["symbol"]).upper().strip()
        if symbol in seen or not is_tradeable_signal_symbol(symbol):
            continue
        bonus = float(row.get("bonus_share_pct") or 0.0)
        rights_raw = str(row.get("right_share_ratio") or "").strip()
        has_rights = bool(rights_raw and rights_raw.lower() not in {"none", "nan", "0", "0%"})
        if bonus < 10.0 and not has_rights:
            continue

        hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=20)
        if hist is None or len(hist) < 8 or not _is_fresh_row(hist, ts):
            continue
        closes = hist["close"].to_numpy(dtype=float)
        if closes[-1] <= 0 or closes[-6] <= 0:
            continue
        ret_5d = closes[-1] / closes[-6] - 1.0
        # Require a visible post-ex-date pullback (modest threshold since prices may be bonus-adjusted)
        if ret_5d > -0.015:
            continue
        turnover = float((hist["close"].tail(5) * hist["volume"].tail(5)).mean())
        if turnover < 100_000:
            continue

        dip_score = min(0.5, abs(ret_5d) * 2.0)
        event_score = 0.45 if has_rights else min(0.45, bonus / 40.0)
        strength = min(1.0, 0.25 + dip_score + event_score)
        seen.add(symbol)
        signals.append(
            AlphaSignal(
                symbol=symbol,
                signal_type=SignalType.EX_DATE_GAP,
                direction=1,
                strength=float(strength),
                confidence=0.70,
                reasoning=(
                    f"Post ex-date dip {ret_5d:.1%} after "
                    f"{'rights ' + rights_raw if has_rights else f'bonus {bonus:.1f}%'}"
                ),
            )
        )
    return signals


# =============================================================================
# 3. UPPER-CIRCUIT CONTINUATION
# =============================================================================

def generate_circuit_continuation_signals_at_date(
    prices_df: pd.DataFrame,
    date: datetime,
    *,
    min_daily_return: float = 0.085,
    min_vol_ratio: float = 1.5,
    max_20d_return: float = 0.60,
    liquid_symbols: Optional[Set[str]] = None,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Ride NEPSE upper-circuit (+8.5%+) breakouts backed by high volume."""
    ts = pd.Timestamp(date)
    symbols = list(symbol_cache.keys()) if symbol_cache is not None else list(prices_df["symbol"].unique())
    signals: List[AlphaSignal] = []

    for symbol in symbols:
        if liquid_symbols is not None and symbol not in liquid_symbols:
            continue
        if not is_tradeable_signal_symbol(symbol):
            continue
        hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=25)
        if hist is None or len(hist) < 22 or not _is_fresh_row(hist, ts, max_stale_days=2):
            continue

        closes = hist["close"].to_numpy(dtype=float)
        highs = hist["high"].to_numpy(dtype=float)
        lows = hist["low"].to_numpy(dtype=float)
        vols = hist["volume"].to_numpy(dtype=float)
        if closes[-1] <= 0 or closes[-2] <= 0 or closes[-21] <= 0:
            continue

        day_ret = closes[-1] / closes[-2] - 1.0
        if day_ret < min_daily_return:
            continue
        # Close near high of day (strong unsatisfied bid pressure)
        day_range = highs[-1] - lows[-1]
        if day_range > 0 and (closes[-1] - lows[-1]) / day_range < 0.75:
            continue

        ret_20d = closes[-1] / closes[-21] - 1.0
        if ret_20d > max_20d_return:
            continue

        med_vol = float(np.median(vols[-21:-1]))
        if med_vol <= 0 or vols[-1] / med_vol < min_vol_ratio:
            continue
        if closes[-1] * vols[-1] < 250_000:
            continue

        vol_ratio = vols[-1] / med_vol
        strength = min(1.0, 0.50 + min(0.30, (vol_ratio - 1.5) * 0.10) + min(0.20, (day_ret - 0.085) * 8.0))
        signals.append(
            AlphaSignal(
                symbol=symbol,
                signal_type=SignalType.CIRCUIT_CONTINUATION,
                direction=1,
                strength=float(strength),
                confidence=0.68,
                reasoning=f"Upper-circuit breakout +{day_ret:.1%}, vol {vol_ratio:.1f}x 20d med",
            )
        )
    return signals


# =============================================================================
# 4. IPO / FPO LISTING MOMENTUM
# =============================================================================

def generate_ipo_momentum_signals_at_date(
    prices_df: pd.DataFrame,
    date: datetime,
    *,
    merger_symbols: Optional[Set[str]] = None,
    ipo_listings: Optional[Dict[str, Dict[str, Any]]] = None,
    min_listing_year: int = 2018,
    min_trading_days: int = 5,
    max_trading_days: int = 45,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Capture post-IPO listing discovery momentum.

    When ``ipo_listings`` (from ``ipo_listings`` SQLite table) is populated,
    restricts to confirmed ``IPO`` rows (excluding FPOs, mutual funds, rights,
    relistings) and anchors to the official ``listing_date`` when present.
    Falls back to the post-2017 first-trading-day proxy when the table is empty.
    """
    ts = pd.Timestamp(date)
    excluded = merger_symbols or set()
    has_ipo_table = bool(ipo_listings)
    symbols = list(symbol_cache.keys()) if symbol_cache is not None else list(prices_df["symbol"].unique())
    signals: List[AlphaSignal] = []

    for symbol in symbols:
        sym_u = str(symbol).upper().strip()
        if sym_u in excluded or not is_tradeable_signal_symbol(sym_u):
            continue

        ipo_meta = ipo_listings.get(sym_u) if ipo_listings else None
        if has_ipo_table:
            if not ipo_meta or ipo_meta.get("issue_type") != "IPO":
                continue

        hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=None)
        if hist is None:
            continue

        official_ldate_str = ipo_meta.get("listing_date") if ipo_meta else None
        if official_ldate_str:
            anchor_dt = pd.Timestamp(official_ldate_str)
            hist_post = hist[hist["date"] >= anchor_dt]
            if hist_post.empty:
                continue
            hist = hist_post
            first_dt = anchor_dt
        else:
            first_dt = pd.Timestamp(hist.iloc[0]["date"])

        n_days = len(hist)
        if n_days < min_trading_days or n_days > max_trading_days:
            continue
        if first_dt.year < min_listing_year:
            continue
        if not _is_fresh_row(hist, ts, max_stale_days=3):
            continue

        closes = hist["close"].to_numpy(dtype=float)
        vols = hist["volume"].to_numpy(dtype=float)
        if closes[-1] <= 0 or closes[0] <= 0 or closes[-min_trading_days] <= 0:
            continue

        # Must have real secondary-market liquidity (past thin initial circuit locks)
        recent_turnover = float(np.mean(closes[-3:] * vols[-3:]))
        if recent_turnover < 200_000:
            continue

        ret_5d = closes[-1] / closes[-min_trading_days] - 1.0
        ret_since_list = closes[-1] / closes[0] - 1.0
        if ret_5d <= 0.01 or ret_since_list <= 0.0:
            continue

        strength = min(1.0, 0.45 + min(0.35, ret_5d * 2.0) + min(0.20, max(0.0, 1.0 - n_days / max_trading_days) * 0.25))
        tag = "official" if official_ldate_str else "proxy"
        signals.append(
            AlphaSignal(
                symbol=symbol,
                signal_type=SignalType.IPO_MOMENTUM,
                direction=1,
                strength=float(strength),
                confidence=0.72 if official_ldate_str else 0.68,
                reasoning=f"IPO day {n_days} ({tag} listed {first_dt.strftime('%Y-%m-%d')}): 5d +{ret_5d:.1%}",
            )
        )
    return signals


# =============================================================================
# 5. SECTOR ROTATION (SYNTHETIC EQUAL-WEIGHT SECTOR INDICES)
# =============================================================================

def generate_sector_rotation_signals_at_date(
    prices_df: pd.DataFrame,
    date: datetime,
    *,
    sector_indices_df: Optional[pd.DataFrame] = None,
    top_sectors: int = 2,
    stocks_per_sector: int = 3,
    liquid_symbols: Optional[Set[str]] = None,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Rotate into top-performing NEPSE sectors using causal synthetic sector indices."""
    ts = pd.Timestamp(date)
    if sector_indices_df is None or sector_indices_df.empty:
        return []
    sub_idx = sector_indices_df.loc[sector_indices_df.index <= ts]
    if len(sub_idx) < 62:
        return []

    # Score each sector by blended 20d + 60d momentum
    sec_scores: List[Tuple[str, float, float]] = []
    for sec in sub_idx.columns:
        s = sub_idx[sec]
        cur, p20, p60 = float(s.iloc[-1]), float(s.iloc[-21]), float(s.iloc[-61])
        if p20 <= 0 or p60 <= 0:
            continue
        r20 = cur / p20 - 1.0
        r60 = cur / p60 - 1.0
        if r20 <= 0.0:
            continue
        score = 0.6 * r20 + 0.4 * r60
        sec_scores.append((sec, score, r20))

    if not sec_scores:
        return []
    sec_scores.sort(key=lambda x: x[1], reverse=True)
    winning_sectors = sec_scores[:top_sectors]

    signals: List[AlphaSignal] = []
    for sec, sec_score, sec_r20 in winning_sectors:
        candidates: List[Tuple[str, float, float]] = []
        for symbol in SECTOR_GROUPS.get(sec, []):
            if liquid_symbols is not None and symbol not in liquid_symbols:
                continue
            if not is_tradeable_signal_symbol(symbol):
                continue
            hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=25)
            if hist is None or len(hist) < 21 or not _is_fresh_row(hist, ts):
                continue
            closes = hist["close"].to_numpy(dtype=float)
            if closes[-1] <= 0 or closes[-21] <= 0:
                continue
            stock_r20 = closes[-1] / closes[-21] - 1.0
            rel_strength = stock_r20 - sec_r20
            if stock_r20 > 0:
                candidates.append((symbol, stock_r20, rel_strength))

        candidates.sort(key=lambda x: x[1], reverse=True)
        for symbol, stock_r20, rel_str in candidates[:stocks_per_sector]:
            strength = min(1.0, 0.40 + min(0.35, sec_score * 3.0) + min(0.25, max(0.0, rel_str) * 2.0))
            signals.append(
                AlphaSignal(
                    symbol=symbol,
                    signal_type=SignalType.SECTOR_ROTATION,
                    direction=1,
                    strength=float(strength),
                    confidence=0.72,
                    reasoning=f"Leading sector {sec} (20d {sec_r20:+.1%}), stock 20d {stock_r20:+.1%}",
                )
            )
    return signals


# =============================================================================
# 6. POST-EARNINGS DRIFT (PEAD)
# =============================================================================

def generate_earnings_drift_signals_at_date(
    prices_df: pd.DataFrame,
    earnings_df: Optional[pd.DataFrame],
    date: datetime,
    *,
    max_days_after: int = 12,
    min_growth: float = 0.15,
    liquid_symbols: Optional[Set[str]] = None,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Post-earnings announcement drift on strong YoY/QoQ profit growth + price confirmation."""
    if earnings_df is None or earnings_df.empty:
        return []
    ts = pd.Timestamp(date)
    win_start = ts - timedelta(days=max_days_after)

    recent = earnings_df[
        (earnings_df["announcement_date"] >= win_start)
        & (earnings_df["announcement_date"] <= ts)
    ]
    if recent.empty:
        return []

    signals: List[AlphaSignal] = []
    seen: Set[str] = set()
    for _, row in recent.iterrows():
        symbol = str(row["symbol"]).upper().strip()
        if symbol in seen or not is_tradeable_signal_symbol(symbol):
            continue
        if liquid_symbols is not None and symbol not in liquid_symbols:
            continue

        # Strictly causal prior earnings history for this symbol
        prior = earnings_df[
            (earnings_df["symbol"] == symbol)
            & (earnings_df["announcement_date"] < row["announcement_date"])
        ]
        if prior.empty:
            continue

        growth = None
        metric_name = "net_profit"
        cur_val = row.get("net_profit")
        if pd.notna(cur_val) and float(cur_val) > 0:
            same_q = prior[(prior["quarter"] == row["quarter"]) & (prior["net_profit"] > 0)]
            base_row = same_q.iloc[-1] if not same_q.empty else prior[prior["net_profit"] > 0].tail(1).squeeze()
            if isinstance(base_row, pd.Series) and pd.notna(base_row.get("net_profit")) and float(base_row["net_profit"]) > 0:
                growth = float(cur_val) / float(base_row["net_profit"]) - 1.0
        if growth is None and pd.notna(row.get("eps")) and float(row["eps"]) > 0:
            metric_name = "eps"
            same_q = prior[(prior["quarter"] == row["quarter"]) & (prior["eps"] > 0)]
            if not same_q.empty:
                growth = float(row["eps"]) / float(same_q.iloc[-1]["eps"]) - 1.0

        if growth is None or growth < min_growth:
            continue

        hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=25)
        if hist is None or len(hist) < 20 or not _is_fresh_row(hist, ts):
            continue
        closes = hist["close"].to_numpy(dtype=float)
        vols = hist["volume"].to_numpy(dtype=float)
        if closes[-1] <= 0 or closes[-4] <= 0:
            continue
        ret_3d = closes[-1] / closes[-4] - 1.0
        if ret_3d < 0.01:
            continue
        med_vol = float(np.median(vols[-20:-1]))
        if med_vol <= 0 or vols[-1] / med_vol < 1.0:
            continue

        strength = min(1.0, 0.45 + min(0.35, growth * 0.6) + min(0.20, ret_3d * 3.0))
        seen.add(symbol)
        signals.append(
            AlphaSignal(
                symbol=symbol,
                signal_type=SignalType.EARNINGS_DRIFT,
                direction=1,
                strength=float(strength),
                confidence=0.75,
                reasoning=(
                    f"PEAD {metric_name} +{growth:.0%} "
                    f"(announced {pd.Timestamp(row['announcement_date']).strftime('%Y-%m-%d')}), 3d {ret_3d:+.1%}"
                ),
            )
        )
    return signals


# =============================================================================
# 7. CALENDAR EFFECTS (DASHAIN / TIHAR / ASHAD YEAR-END)
# =============================================================================

_ASHAD_END_DATES = tuple(ashad_end_dates(2074, 2085))


def generate_calendar_festival_signals_at_date(
    prices_df: pd.DataFrame,
    date: datetime,
    *,
    liquid_symbols: Optional[Set[str]] = None,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Capture Ashad fiscal-year-end liquidity rebound and Dashain/Tihar remittance flows."""
    ts = pd.Timestamp(date)
    d: date_type = ts.date()

    # Check active calendar window
    in_ashad_rebound = any(-5 <= (d - ae).days <= 12 for ae in _ASHAD_END_DATES)
    dashain_wins = festival_windows("dashain")
    tihar_wins = festival_windows("tihar")
    in_pre_dashain = any(5 <= (start - d).days <= 18 for start, _ in dashain_wins)
    in_post_tihar = any(1 <= (d - end).days <= 12 for _, end in tihar_wins)

    if not (in_ashad_rebound or in_pre_dashain or in_post_tihar):
        return []

    tag = (
        "Ashad FY-end rebound"
        if in_ashad_rebound
        else ("Pre-Dashain liquidity" if in_pre_dashain else "Post-Tihar liquidity")
    )

    symbols = list(symbol_cache.keys()) if symbol_cache is not None else list(prices_df["symbol"].unique())
    candidates: List[Tuple[str, float, str]] = []

    for symbol in symbols:
        if liquid_symbols is not None and symbol not in liquid_symbols:
            continue
        if not is_tradeable_signal_symbol(symbol):
            continue
        sec = _symbol_sector(symbol)
        if not in_ashad_rebound and sec not in _FESTIVAL_SECTORS:
            continue

        hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=25)
        if hist is None or len(hist) < 21 or not _is_fresh_row(hist, ts):
            continue
        closes = hist["close"].to_numpy(dtype=float)
        vols = hist["volume"].to_numpy(dtype=float)
        if closes[-1] <= 0 or closes[-11] <= 0 or closes[-21] <= 0:
            continue
        ret_10d = closes[-1] / closes[-11] - 1.0
        ret_20d = closes[-1] / closes[-21] - 1.0
        turnover = float(np.mean(closes[-5:] * vols[-5:]))
        if turnover < 300_000:
            continue

        if in_ashad_rebound:
            # Look for quality liquid stocks sold down into Ashad margin-call pressure
            if -0.20 <= ret_20d <= -0.02:
                score = min(1.0, 0.45 + abs(ret_20d) * 2.5)
                candidates.append((symbol, score, f"{tag}: 20d dip {ret_20d:.1%}"))
        else:
            # Festive remittance flow: favor liquid leaders with positive 10d trend
            if 0.01 <= ret_10d <= 0.20:
                score = min(1.0, 0.45 + ret_10d * 2.5)
                candidates.append((symbol, score, f"{tag} ({sec}): 10d {ret_10d:+.1%}"))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [
        AlphaSignal(
            symbol=sym,
            signal_type=SignalType.CALENDAR_FESTIVAL,
            direction=1,
            strength=float(score),
            confidence=0.66,
            reasoning=reason,
        )
        for sym, score, reason in candidates[:10]
    ]


# =============================================================================
# 8. NRB MONETARY POLICY REACTION
# =============================================================================

def generate_nrb_policy_signals_at_date(
    prices_df: pd.DataFrame,
    date: datetime,
    *,
    max_days_after: int = 12,
    liquid_symbols: Optional[Set[str]] = None,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Post-NRB Monetary Policy follow-through in rate-sensitive BFI sectors."""
    ts = pd.Timestamp(date)
    d = ts.date()
    matched_policy = None
    for pdate in NRB_POLICY_DATES:
        delta = (d - pdate).days
        if 0 <= delta <= max_days_after:
            matched_policy = pdate
            break
    if matched_policy is None:
        return []

    symbols = [s for sec in _BFI_SECTORS for s in SECTOR_GROUPS.get(sec, [])]
    signals: List[AlphaSignal] = []

    for symbol in symbols:
        if liquid_symbols is not None and symbol not in liquid_symbols:
            continue
        if not is_tradeable_signal_symbol(symbol):
            continue
        hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=25)
        if hist is None or len(hist) < 21 or not _is_fresh_row(hist, ts):
            continue
        closes = hist["close"].to_numpy(dtype=float)
        vols = hist["volume"].to_numpy(dtype=float)
        if closes[-1] <= 0 or closes[-6] <= 0:
            continue
        ret_5d = closes[-1] / closes[-6] - 1.0
        med_vol = float(np.median(vols[-20:-1]))
        if ret_5d < 0.02 or med_vol <= 0 or vols[-1] / med_vol < 1.2:
            continue

        vol_ratio = vols[-1] / med_vol
        strength = min(1.0, 0.45 + min(0.35, ret_5d * 3.0) + min(0.20, (vol_ratio - 1.2) * 0.15))
        signals.append(
            AlphaSignal(
                symbol=symbol,
                signal_type=SignalType.NRB_POLICY,
                direction=1,
                strength=float(strength),
                confidence=0.72,
                reasoning=(
                    f"Post-NRB policy ({matched_policy.isoformat()}) BFI surge: "
                    f"5d {ret_5d:+.1%}, vol {vol_ratio:.1f}x"
                ),
            )
        )
    return signals


# =============================================================================
# 9. SECTOR LEAD-LAG (BELLWETHER -> LAGGARD CATCH-UP)
# =============================================================================

def generate_lead_lag_signals_at_date(
    prices_df: pd.DataFrame,
    date: datetime,
    *,
    leader_min_ret5d: float = 0.04,
    min_spread: float = 0.03,
    liquid_symbols: Optional[Set[str]] = None,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Buy liquid sector laggards after top-turnover bellwethers in their sector break out."""
    ts = pd.Timestamp(date)
    signals: List[AlphaSignal] = []

    for sector, syms in SECTOR_GROUPS.items():
        if len(syms) < 6:
            continue
        sec_stats: List[Tuple[str, float, float, float]] = []  # (symbol, avg_turnover, ret_5d, ret_20d)
        for symbol in syms:
            if not is_tradeable_signal_symbol(symbol):
                continue
            hist = _history_slice(prices_df, symbol_cache, symbol, ts, tail=25)
            if hist is None or len(hist) < 21 or not _is_fresh_row(hist, ts):
                continue
            closes = hist["close"].to_numpy(dtype=float)
            vols = hist["volume"].to_numpy(dtype=float)
            if closes[-1] <= 0 or closes[-6] <= 0 or closes[-21] <= 0:
                continue
            avg_to = float(np.mean(closes[-20:] * vols[-20:]))
            if avg_to < 100_000:
                continue
            ret_5d = closes[-1] / closes[-6] - 1.0
            ret_20d = closes[-1] / closes[-21] - 1.0
            sec_stats.append((symbol, avg_to, ret_5d, ret_20d))

        if len(sec_stats) < 5:
            continue
        sec_stats.sort(key=lambda x: x[1], reverse=True)
        leaders = sec_stats[:3]
        leader_ret = float(np.mean([x[2] for x in leaders]))
        if leader_ret < leader_min_ret5d:
            continue

        leader_syms = {x[0] for x in leaders}
        laggards: List[Tuple[str, float, float]] = []
        for symbol, _to, ret_5d, ret_20d in sec_stats[3:]:
            if symbol in leader_syms:
                continue
            if liquid_symbols is not None and symbol not in liquid_symbols:
                continue
            spread = leader_ret - ret_5d
            if spread >= min_spread and -0.03 <= ret_5d <= 0.02 and ret_20d >= -0.10:
                laggards.append((symbol, spread, ret_5d))

        laggards.sort(key=lambda x: x[1], reverse=True)
        for symbol, spread, ret_5d in laggards[:2]:
            strength = min(1.0, 0.40 + min(0.60, spread * 5.0))
            signals.append(
                AlphaSignal(
                    symbol=symbol,
                    signal_type=SignalType.LEAD_LAG,
                    direction=1,
                    strength=float(strength),
                    confidence=0.70,
                    reasoning=(
                        f"{sector} bellwethers 5d {leader_ret:+.1%} vs "
                        f"{symbol} {ret_5d:+.1%} (spread {spread:.1%})"
                    ),
                )
            )
    return signals


# =============================================================================
# 10. BROKER CONCENTRATION / INFORMED TRADING (FLOORSHEET AGGREGATES)
# =============================================================================

def load_broker_flow_df(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load daily broker-flow aggregates (no raw floorsheet scan needed)."""
    try:
        df = pd.read_sql_query(
            """
            SELECT
                v2.symbol,
                v2.as_of_date AS date,
                v2.hhi_buy_norm,
                v2.hhi_sell_norm,
                v2.circular_score,
                v2.self_trade_pct,
                v2.smart_money_score,
                v2.pump_score,
                v2.total_volume,
                v2.n_trades,
                COALESCE(bs.top5_net_share, 0.0) AS top5_net_share,
                COALESCE(bs.accumulation_score, 0.0) AS accumulation_score,
                COALESCE(bm.pin_proxy, 0.0) AS pin_proxy,
                COALESCE(bm.micro_score, 0.0) AS micro_score,
                COALESCE(bm.kyle_significant, 0) AS kyle_significant
            FROM broker_signals_v2 v2
            LEFT JOIN broker_signal_scores bs
                ON bs.symbol = v2.symbol AND bs.as_of_date = v2.as_of_date
            LEFT JOIN broker_microstructure bm
                ON bm.symbol = v2.symbol AND bm.as_of_date = v2.as_of_date
            ORDER BY v2.as_of_date ASC, v2.symbol ASC
            """,
            conn,
        )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    return df


def generate_informed_trading_signals_at_date(
    prices_df: pd.DataFrame,
    broker_flow_df: Optional[pd.DataFrame],
    date: datetime,
    *,
    lookback_days: int = 5,
    min_smart_money: float = 0.12,
    liquid_symbols: Optional[Set[str]] = None,
    symbol_cache: Optional[Dict[str, Tuple[pd.DataFrame, np.ndarray]]] = None,
) -> List[AlphaSignal]:
    """Emit causal informed-trading buy signals from prior-day broker concentration.

    Strict no-lookahead: uses only ``as_of_date < date`` aggregates and filters
    out circular / self-trade pump flags.
    """
    if broker_flow_df is None or broker_flow_df.empty:
        return []
    ts = pd.Timestamp(date)
    start_ts = ts - pd.Timedelta(days=lookback_days)
    window = broker_flow_df[(broker_flow_df["date"] >= start_ts) & (broker_flow_df["date"] < ts)]
    if window.empty:
        return []

    signals: List[AlphaSignal] = []
    for symbol, grp in window.groupby("symbol"):
        sym_u = str(symbol).upper().strip()
        if not is_tradeable_signal_symbol(sym_u):
            continue
        if liquid_symbols is not None and sym_u not in liquid_symbols:
            continue

        # Reject wash / circular / pump activity anywhere in the lookback window
        if float(grp["pump_score"].max()) >= 0.05:
            continue
        if float(grp["self_trade_pct"].max()) >= 0.05:
            continue
        if float(grp["circular_score"].max()) >= 0.25:
            continue

        avg_smart = float(grp["smart_money_score"].mean())
        avg_hhi_buy = float(grp["hhi_buy_norm"].mean())
        avg_hhi_sell = float(grp["hhi_sell_norm"].mean())
        avg_top5 = float(grp["top5_net_share"].mean())
        avg_micro = float(grp["micro_score"].mean())
        max_trades = int(grp["n_trades"].max())
        max_vol = int(grp["total_volume"].max())

        if max_trades < 20 or max_vol < 5000:
            continue

        concentrated_buy = (
            avg_smart >= min_smart_money
            or (avg_hhi_buy >= 0.22 and avg_hhi_sell <= 0.35 and avg_top5 >= 0.25)
        )
        if not concentrated_buy:
            continue

        hist = _history_slice(prices_df, symbol_cache, sym_u, ts, tail=5)
        if hist is None or not _is_fresh_row(hist, ts, max_stale_days=3):
            continue

        strength = min(
            1.0,
            0.35 + 0.45 * min(1.0, avg_smart / 0.50) + 0.12 * min(1.0, avg_top5) + 0.08 * min(1.0, avg_micro),
        )
        confidence = min(0.85, 0.58 + 0.08 * min(3, len(grp)))
        signals.append(
            AlphaSignal(
                symbol=sym_u,
                signal_type=SignalType.INFORMED_TRADING,
                direction=1,
                strength=float(strength),
                confidence=float(confidence),
                reasoning=(
                    f"Broker accumulation ({len(grp)}d): smart={avg_smart:.2f}, "
                    f"hhi_buy={avg_hhi_buy:.2f}, top5={avg_top5:.0%}, micro={avg_micro:.2f}"
                ),
            )
        )

    signals.sort(key=lambda s: s.strength * s.confidence, reverse=True)
    return signals

