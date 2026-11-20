#!/usr/bin/env python3
"""Run C5 paper backtest baseline vs NEPSE, with menaceXnadin cross-check.

Usage:
    python scripts/validation/run_baseline.py
    python scripts/validation/run_baseline.py --force
    python scripts/validation/run_baseline.py --skip-topup   # use DB as-is
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.backtesting.results_store import has_run, save_run
from backend.backtesting.simple_backtest import CAPITAL_SCENARIOS, run_backtest
from backend.quant_pro.database import get_db_path
from backend.quant_pro.paths import get_runtime_dir
from scripts.validation.baseline_crosscheck import (
    crosscheck_symbols,
    pick_liquid_symbols,
)


def _load_c5_config() -> dict:
    path = ROOT / "data" / "strategy_registry" / "builtin" / "default_c5.json"
    return json.loads(path.read_text())["config"]


def _db_date_range(conn: sqlite3.Connection) -> tuple[str, str]:
    row = conn.execute("SELECT MIN(date), MAX(date) FROM stock_prices").fetchone()
    return str(row[0])[:10], str(row[1])[:10]


def _nepse_buy_hold(conn: sqlite3.Connection, start: str, end: str) -> dict:
    df = pd.read_sql_query(
        """
        SELECT date, close FROM stock_prices
        WHERE symbol = 'NEPSE' AND date >= ? AND date <= ?
        ORDER BY date
        """,
        conn,
        params=(start, end),
        parse_dates=["date"],
    )
    if len(df) < 2:
        return {"total_return": None, "start_close": None, "end_close": None, "n_days": 0}
    start_close = float(df.iloc[0]["close"])
    end_close = float(df.iloc[-1]["close"])
    total = (end_close / start_close) - 1.0 if start_close else None
    years = max((df.iloc[-1]["date"] - df.iloc[0]["date"]).days / 365.25, 1e-9)
    ann = (1 + total) ** (1 / years) - 1 if total is not None and total > -1 else None
    return {
        "total_return": total,
        "annualized_return": ann,
        "start_close": start_close,
        "end_close": end_close,
        "n_days": int(len(df)),
        "start_date": str(df.iloc[0]["date"].date()),
        "end_date": str(df.iloc[-1]["date"].date()),
    }


def _result_metrics(result) -> dict:
    final_nav = result.final_nav
    return {
        "initial_capital": result.initial_capital,
        "total_contributed": result.total_contributed,
        "contributions_count": len(result.contributions),
        "final_nav": final_nav,
        "total_return": result.total_return,
        "annualized_return": result.annualized_return,
        "twr_total_return": result.twr_total_return,
        "twr_annualized_return": result.twr_annualized_return,
        "xirr": result.xirr,
        "volatility": result.volatility,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "max_drawdown": result.max_drawdown,
        "max_drawdown_duration": result.max_drawdown_duration,
        "calmar_ratio": result.calmar_ratio,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "avg_win": result.avg_win,
        "avg_loss": result.avg_loss,
        "profit_factor": result.profit_factor,
        "avg_holding_days": result.avg_holding_days,
        "total_pnl": result.total_pnl,
        "total_fees_paid": result.total_fees_paid,
        "by_signal_type": result.by_signal_type(),
        "by_exit_reason": result.by_exit_reason(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C5 paper baseline vs NEPSE")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None, help="Default: MAX(date) in stock_prices")
    parser.add_argument("--force", action="store_true", help="Overwrite existing baseline folder")
    parser.add_argument("--liquid", type=int, default=20, help="Cross-check this many liquid symbols")
    args = parser.parse_args(argv)

    db_path = get_db_path()
    if not Path(db_path).exists():
        print(f"DB missing: {db_path}. Run: python setup_data.py", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    db_min, db_max = _db_date_range(conn)
    start = args.start
    end = args.end or db_max
    if start > end:
        print(f"--start {start} after end {end}", file=sys.stderr)
        return 1

    run_date = date.today().isoformat()
    out_dir = get_runtime_dir() / "baselines" / run_date
    if out_dir.exists() and not args.force:
        print(f"Baseline already at {out_dir} (pass --force to redo)")
        conn.close()
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = get_runtime_dir() / "crosscheck"

    print(f"DB range {db_min} → {db_max}; backtest {start} → {end}")
    liquid = pick_liquid_symbols(conn, start, end, n=args.liquid)
    check_syms = liquid + (["NEPSE"] if "NEPSE" not in liquid else [])
    print(f"Cross-checking {len(check_syms)} symbols vs menaceXnadin…")
    xrows = crosscheck_symbols(conn, check_syms, start=start, end=end, cache_dir=cache_dir)
    excluded = {r["symbol"] for r in xrows if r.get("exclude")}
    # Never exclude the index from price load via exclude_symbols — NEPSE is used for regime;
    # only stock exclusions apply.
    exclude_symbols = {s for s in excluded if s.upper() != "NEPSE"}
    print(f"Exclude ({len(exclude_symbols)}): {sorted(exclude_symbols) or 'none'}")

    cfg = _load_c5_config()
    allowed = {
        "holding_days", "max_positions", "signal_types",
        "rebalance_frequency", "use_trailing_stop", "trailing_stop_pct",
        "stop_loss_pct", "use_regime_filter", "sector_limit",
        "regime_max_positions", "bear_threshold", "profit_target_pct",
        "event_exit_mode", "regime_sector_limits",
    }
    base_kwargs = {k: v for k, v in cfg.items() if k in allowed}

    scenario_results = {}
    scenario_run_ids = {}
    summary_chunks = []
    for scenario_key, spec in CAPITAL_SCENARIOS.items():
        scen_cfg = dict(base_kwargs)
        scen_cfg["initial_capital"] = spec["initial_capital"]
        scen_cfg["monthly_contribution"] = spec["monthly_contribution"]
        if exclude_symbols:
            scen_cfg["exclude_symbols"] = sorted(exclude_symbols)

        existing_id = None if args.force else has_run(
            strategy_id="default_c5",
            scenario=scenario_key,
            config=scen_cfg,
            data_end=db_max,
            start_date=start,
            end_date=end,
        )
        print(f"Running C5 backtest [{scenario_key}: {spec['label']}]…")
        result = run_backtest(
            start_date=start,
            end_date=end,
            exclude_symbols=exclude_symbols or None,
            initial_capital=spec["initial_capital"],
            monthly_contribution=spec["monthly_contribution"],
            **base_kwargs,
        )
        print(result.summary())
        run_id = existing_id if existing_id is not None else save_run(
            strategy_id="default_c5",
            scenario=scenario_key,
            config=scen_cfg,
            result=result,
            data_end=db_max,
        )
        scenario_results[scenario_key] = result
        scenario_run_ids[scenario_key] = run_id
        summary_chunks.append(f"=== SCENARIO: {scenario_key} ({spec['label']}) [run_id={run_id}] ===\n{result.summary()}")

        if result.trades:
            trades_df = pd.DataFrame(
                [
                    {
                        "symbol": t.symbol,
                        "signal_date": t.signal_date,
                        "entry_date": t.entry_date,
                        "entry_price": t.entry_price,
                        "shares": t.shares,
                        "exit_date": t.exit_date,
                        "exit_price": t.exit_price,
                        "signal_type": t.signal_type,
                        "exit_reason": t.exit_reason,
                        "gross_return": t.gross_return,
                        "net_return": t.net_return,
                        "net_pnl": t.net_pnl,
                        "holding_days": t.holding_days,
                    }
                    for t in result.trades
                    if t.net_return is not None
                ]
            )
            trades_df.to_csv(out_dir / f"trades_{scenario_key}.csv", index=False)
            if scenario_key == "lump_10l":
                trades_df.to_csv(out_dir / "trades.csv", index=False)

        if result.daily_nav:
            nav_df = pd.DataFrame(result.daily_nav, columns=["date", "nav"])
            nav_df.to_csv(out_dir / f"nav_{scenario_key}.csv", index=False)
            if scenario_key == "lump_10l":
                nav_df.to_csv(out_dir / "nav.csv", index=False)

    nepse = _nepse_buy_hold(conn, start, end)
    conn.close()

    metrics = {
        "run_date": run_date,
        "strategy_id": "default_c5",
        "window": {"start": start, "end": end, "db_min": db_min, "db_max": db_max},
        "strategy": _result_metrics(scenario_results["lump_10l"]),
        "scenarios": {k: _result_metrics(v) for k, v in scenario_results.items()},
        "backtests_db_run_ids": scenario_run_ids,
        "nepse_buy_hold": nepse,
        "crosscheck": xrows,
        "excluded_symbols": sorted(exclude_symbols),
        "caveats": [
            "in-sample relative to C5 parameter history",
            "no slippage in base engine",
            "limit-locked days still fill",
            "survivorship bias: delisted stocks missing",
        ],
        "data_sources": [
            {
                "name": "nlethetech/nepse-quant-terminal releases v3.0",
                "use": "bundled nepse_market_data.db (prices, earnings, corporate actions through 2026-04-15)",
            },
            {
                "name": "Merolagani TechnicalChartHandler (isAdjust=1)",
                "use": "incremental price top-up after bundled cutoff",
            },
            {
                "name": "menaceXnadin/nepse-historical-market-data-csv",
                "use": "adjusted CSV cross-check; exclude symbols with >5% of days >1% close mismatch",
            },
        ],
    }

    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    (out_dir / "summary.txt").write_text(
        "\n\n".join(summary_chunks)
        + "\n\nNEPSE buy-and-hold:\n"
        + json.dumps(nepse, indent=2)
        + "\n\nExcluded: "
        + ", ".join(sorted(exclude_symbols) or ["none"])
        + "\n"
    )

    print(f"\nWrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
