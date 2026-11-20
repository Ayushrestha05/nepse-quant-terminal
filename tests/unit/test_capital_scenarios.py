"""Unit tests for NEPSE capital scenarios, BS monthly deposits, XIRR, trade store, and no-lookahead."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.backtesting.nepse_event_signals import (
    build_synthetic_sector_indices,
    generate_book_closure_runup_signals_at_date,
    generate_calendar_festival_signals_at_date,
    generate_circuit_continuation_signals_at_date,
    generate_earnings_drift_signals_at_date,
    generate_ex_date_gap_signals_at_date,
    generate_ipo_momentum_signals_at_date,
    generate_lead_lag_signals_at_date,
    generate_nrb_policy_signals_at_date,
    generate_sector_rotation_signals_at_date,
    load_merger_symbols,
    load_quarterly_earnings_df,
)
from backend.backtesting.results_store import has_run, load_latest_runs, load_run_trades, save_run
from backend.backtesting.simple_backtest import (
    CAPITAL_SCENARIOS,
    BacktestResult,
    Trade,
    build_symbol_price_cache,
    compute_xirr,
    effective_max_positions_for_nav,
    load_all_prices,
    load_corporate_actions,
    run_backtest,
)
from backend.quant_pro.database import get_db_path
from backend.quant_pro.nepal_calendar import bs_month_starts, to_bs


def test_bs_month_starts_land_on_first_trading_day_of_each_bs_month():
    # Generate synthetic NEPSE Sun-Thu trading days spanning 4 BS months (2024-03-01 .. 2024-07-31)
    days = []
    cur = date(2024, 3, 1)
    while cur <= date(2024, 7, 31):
        # NEPSE trades Sun (6) - Thu (3)
        if cur.weekday() in {6, 0, 1, 2, 3}:
            days.append(cur)
        cur += timedelta(days=1)

    starts = bs_month_starts(days)
    assert len(starts) >= 5
    # Each returned date must be strictly the earliest trading day for its BS (year, month)
    seen_ym = set()
    for d in starts:
        bs = to_bs(d)
        ym = (bs.year, bs.month)
        assert ym not in seen_ym
        seen_ym.add(ym)
        # No earlier trading day in `days` can share the same BS (year, month)
        earlier = [x for x in days if x < d and (to_bs(x).year, to_bs(x).month) == ym]
        assert earlier == []


def test_compute_xirr_exact_on_known_cashflows():
    # Invest 100,000 for exactly 365 days (non-leap 2023) -> grows to 110,000 => XIRR == 10.00%
    r1 = compute_xirr([(date(2023, 1, 1), -100_000.0), (date(2024, 1, 1), 110_000.0)])
    assert r1 is not None
    assert abs(r1 - 0.10) < 1e-6

    # Two deposits: -1000 at t=0, -1000 at t=182.5d, compounded at 12%/yr -> exact terminal value
    rate = 0.12
    t0 = date(2024, 1, 1)
    t_mid = date(2024, 7, 2)  # 183 days
    t_end = date(2025, 1, 1)  # 366 days
    end_val = 1000.0 * (1 + rate) ** ((t_end - t0).days / 365.0) + 1000.0 * (1 + rate) ** ((t_end - t_mid).days / 365.0)
    r2 = compute_xirr([(t0, -1000.0), (t_mid, -1000.0), (t_end, end_val)])
    assert r2 is not None
    assert abs(r2 - rate) < 1e-4


def test_small_account_5k_opens_positions_and_receives_bs_deposits():
    assert set(CAPITAL_SCENARIOS.keys()) == {"lump_10l", "lump_1l", "sip_5k"}
    assert effective_max_positions_for_nav(5_000.0, 5) == 1
    assert effective_max_positions_for_nav(1_000_000.0, 5) == 5

    # Run a short 6-month window on real DB with 5K start + 5K/BS month
    res = run_backtest(
        start_date="2024-01-01",
        end_date="2024-08-31",
        holding_days=20,
        max_positions=5,
        signal_types=["sector_rotation", "momentum"],
        initial_capital=5_000.0,
        monthly_contribution=5_000.0,
        rebalance_frequency=5,
    )
    assert len(res.contributions) >= 6, f"Expected >=6 BS month deposits, got {len(res.contributions)}"
    # Every contribution must fall on a BS month start strictly after the first trading day
    first_dt = pd.Timestamp(res.daily_nav[0][0]).date()
    trading_days = [pd.Timestamp(d).date() for d, _ in res.daily_nav]
    expected_starts = {d for d in bs_month_starts(trading_days) if d > first_dt}
    actual_dates = {pd.Timestamp(d).date() for d, _ in res.contributions}
    assert actual_dates == expected_starts
    # Account must actually open trades despite starting at NPR 5,000
    assert res.total_trades >= 1
    assert res.xirr is not None


def test_results_store_roundtrip_and_skip_cache(tmp_path: Path):
    db_file = tmp_path / "test_backtests.db"
    t = Trade(
        symbol="NABIL",
        entry_date=datetime(2024, 2, 1),
        entry_price=500.0,
        shares=20,
        position_value=10_000.0,
        buy_fees=60.0,
        sell_fees=65.0,
        signal_date=datetime(2024, 1, 31),
        exit_date=datetime(2024, 3, 1),
        exit_price=550.0,
        signal_type="sector_rotation",
        exit_reason="holding_period",
        max_price=560.0,
    )
    res = BacktestResult(
        trades=[t],
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 3, 31),
        holding_period=20,
        initial_capital=5_000.0,
        daily_nav=[(datetime(2024, 1, 1), 5_000.0), (datetime(2024, 2, 1), 10_000.0), (datetime(2024, 3, 31), 10_875.0)],
        contributions=[(datetime(2024, 2, 1), 5_000.0)],
        daily_nav_detail=[
            (datetime(2024, 1, 1), 5_000.0, 5_000.0, 0.0),
            (datetime(2024, 2, 1), 10_000.0, 0.0, 10_000.0),
            (datetime(2024, 3, 31), 10_875.0, 10_875.0, 0.0),
        ],
    )
    cfg = {"signal_types": ["sector_rotation"], "initial_capital": 5000.0, "monthly_contribution": 5000.0}
    assert has_run(
        strategy_id="nepse_sector_rotation",
        scenario="sip_5k",
        config=cfg,
        data_end="2026-11-19",
        start_date="2024-01-01",
        end_date="2024-03-31",
        db_path=db_file,
    ) is None

    run_id = save_run(
        strategy_id="nepse_sector_rotation",
        scenario="sip_5k",
        config=cfg,
        result=res,
        data_end="2026-11-19",
        db_path=db_file,
    )
    assert has_run(
        strategy_id="nepse_sector_rotation",
        scenario="sip_5k",
        config=cfg,
        data_end="2026-11-19",
        start_date="2024-01-01",
        end_date="2024-03-31",
        db_path=db_file,
    ) == run_id

    trades_df = load_run_trades(run_id, db_path=db_file)
    assert len(trades_df) == 1
    assert trades_df.iloc[0]["symbol"] == "NABIL"
    assert float(trades_df.iloc[0]["buy_fees"]) == 60.0
    latest = load_latest_runs(data_end="2026-11-19", db_path=db_file)
    assert len(latest) == 1 and latest[0]["run_id"] == run_id


def test_new_signal_generators_have_no_lookahead():
    """Truncating all market/event data strictly to <= T must yield identical signals at T."""
    conn = sqlite3.connect(str(get_db_path()))
    prices_full = load_all_prices(conn)
    corp_full = load_corporate_actions(conn)
    mergers = load_merger_symbols(conn)
    earn_full = load_quarterly_earnings_df(conn)
    conn.close()

    # Pick a date with active data & near NRB/Ashad/earnings windows
    cutoff = pd.Timestamp("2024-07-29")  # 3 days after 2024-07-26 NRB policy & post-Ashad
    prices_trunc = prices_full[prices_full["date"] <= cutoff].copy()
    earn_trunc = earn_full[earn_full["announcement_date"] <= cutoff].copy()
    # For ex_date_gap, bookclose <= cutoff; for book_closure_runup, statutory 15-day pre-notice window
    corp_ex_trunc = corp_full[corp_full["bookclose_date"] <= cutoff].copy()
    corp_bc_trunc = corp_full[corp_full["bookclose_date"] <= cutoff + timedelta(days=15)].copy()

    cache_full = build_symbol_price_cache(prices_full)
    cache_trunc = build_symbol_price_cache(prices_trunc)
    sec_full = build_synthetic_sector_indices(prices_full)
    sec_trunc = build_synthetic_sector_indices(prices_trunc)

    def _sig_key(sigs):
        return sorted((s.symbol, s.signal_type.value, round(s.strength, 6)) for s in sigs)

    checks = [
        (
            "book_closure_runup",
            generate_book_closure_runup_signals_at_date(prices_full, corp_full, cutoff, symbol_cache=cache_full),
            generate_book_closure_runup_signals_at_date(prices_trunc, corp_bc_trunc, cutoff, symbol_cache=cache_trunc),
        ),
        (
            "ex_date_gap",
            generate_ex_date_gap_signals_at_date(prices_full, corp_full, cutoff, symbol_cache=cache_full),
            generate_ex_date_gap_signals_at_date(prices_trunc, corp_ex_trunc, cutoff, symbol_cache=cache_trunc),
        ),
        (
            "circuit_continuation",
            generate_circuit_continuation_signals_at_date(prices_full, cutoff, symbol_cache=cache_full),
            generate_circuit_continuation_signals_at_date(prices_trunc, cutoff, symbol_cache=cache_trunc),
        ),
        (
            "ipo_momentum",
            generate_ipo_momentum_signals_at_date(prices_full, cutoff, merger_symbols=mergers, symbol_cache=cache_full),
            generate_ipo_momentum_signals_at_date(prices_trunc, cutoff, merger_symbols=mergers, symbol_cache=cache_trunc),
        ),
        (
            "sector_rotation",
            generate_sector_rotation_signals_at_date(prices_full, cutoff, sector_indices_df=sec_full, symbol_cache=cache_full),
            generate_sector_rotation_signals_at_date(prices_trunc, cutoff, sector_indices_df=sec_trunc, symbol_cache=cache_trunc),
        ),
        (
            "earnings_drift",
            generate_earnings_drift_signals_at_date(prices_full, earn_full, cutoff, symbol_cache=cache_full),
            generate_earnings_drift_signals_at_date(prices_trunc, earn_trunc, cutoff, symbol_cache=cache_trunc),
        ),
        (
            "calendar_festival",
            generate_calendar_festival_signals_at_date(prices_full, cutoff, symbol_cache=cache_full),
            generate_calendar_festival_signals_at_date(prices_trunc, cutoff, symbol_cache=cache_trunc),
        ),
        (
            "nrb_policy",
            generate_nrb_policy_signals_at_date(prices_full, cutoff, symbol_cache=cache_full),
            generate_nrb_policy_signals_at_date(prices_trunc, cutoff, symbol_cache=cache_trunc),
        ),
        (
            "lead_lag",
            generate_lead_lag_signals_at_date(prices_full, cutoff, symbol_cache=cache_full),
            generate_lead_lag_signals_at_date(prices_trunc, cutoff, symbol_cache=cache_trunc),
        ),
    ]
    for name, s_full, s_trunc in checks:
        assert _sig_key(s_full) == _sig_key(s_trunc), f"Lookahead mismatch in {name}"
