"""Parity and performance regression test for the cached backtest engine."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from backend.backtesting.simple_backtest import run_backtest
from backend.quant_pro.database import get_db_path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "c5_2023q1_reference.json"
C5_CONFIG_PATH = ROOT / "data" / "strategy_registry" / "builtin" / "default_c5.json"


def test_c5_2023q1_backtest_parity():
    if not Path(get_db_path()).exists():
        pytest.skip("market database not present")

    ref = json.loads(FIXTURE_PATH.read_text())
    cfg = json.loads(C5_CONFIG_PATH.read_text())["config"]

    t0 = time.perf_counter()
    res = run_backtest(ref["start_date"], ref["end_date"], **cfg)
    wall = time.perf_counter() - t0
    print(f"\nC5 2023Q1 parity wall time: {wall:.2f}s (reference uncached: {ref['wall_seconds']:.2f}s)")

    actual_trades = [
        (
            t.symbol,
            str(t.entry_date)[:10],
            str(t.exit_date)[:10] if t.exit_date is not None else None,
        )
        for t in res.trades
    ]
    expected_trades = [
        (t["symbol"], t["entry_date"], t["exit_date"])
        for t in ref["trades"]
    ]

    assert len(actual_trades) == ref["trade_count"]
    assert actual_trades == expected_trades

    actual_nav = float(res.daily_nav[-1][1])
    rel_diff = abs(actual_nav - ref["final_nav"]) / ref["final_nav"]
    assert rel_diff <= 0.001, f"NAV drift {rel_diff:.4%}: actual={actual_nav:.2f} vs ref={ref['final_nav']:.2f}"
