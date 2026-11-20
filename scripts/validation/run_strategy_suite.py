#!/usr/bin/env python3
"""Parallel NEPSE strategy suite runner + vault report generator.

Phases:
  1. Run 9 NEPSE solo strategies x 3 CAPITAL_SCENARIOS (27 runs).
  2. Select combo_top3_sharpe, combo_top5_sharpe, combo_c5_plus_best strictly
     from 2020-2024 in-sample solo Sharpe ratios and persist their registry JSONs.
  3. Run the 5 combinations + default_c5 re-run x 3 CAPITAL_SCENARIOS (18 runs).
  4. Generate per-strategy reports, the Strategy Comparison report with
     account-value charts, and update the vault Run Tracker.

Every run persists trades, daily NAV, and BS monthly contributions into
`data/backtests.db` and skips unchanged runs unless `--force` is passed.

Usage:
    python scripts/validation/run_strategy_suite.py
    python scripts/validation/run_strategy_suite.py --force --workers 4
    python scripts/validation/run_strategy_suite.py --reports-only
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.backtesting.results_store import (
    has_run,
    load_latest_runs,
    load_run_nav,
    save_run,
)
from backend.backtesting.simple_backtest import CAPITAL_SCENARIOS, run_backtest
from backend.quant_pro.database import get_db_path
from backend.trading.strategy_registry import BUILTIN_STRATEGY_DIR, load_strategy

SOLO_STRATEGY_IDS: List[str] = [
    "nepse_book_closure_runup",
    "nepse_ex_date_gap",
    "nepse_circuit_continuation",
    "nepse_ipo_momentum",
    "nepse_sector_rotation",
    "nepse_earnings_drift",
    "nepse_calendar_festival",
    "nepse_nrb_policy",
    "nepse_lead_lag",
]

FIXED_COMBO_IDS: List[str] = [
    "combo_event_driven",
    "combo_trend",
]

SELECTED_COMBO_IDS: List[str] = [
    "combo_top3_sharpe",
    "combo_top5_sharpe",
    "combo_c5_plus_best",
]

ALLOWED_BT_KEYS = {
    "holding_days",
    "max_positions",
    "signal_types",
    "rebalance_frequency",
    "use_trailing_stop",
    "trailing_stop_pct",
    "stop_loss_pct",
    "use_regime_filter",
    "sector_limit",
    "regime_max_positions",
    "bear_threshold",
    "profit_target_pct",
    "event_exit_mode",
    "regime_sector_limits",
}


def _db_max_date() -> str:
    conn = sqlite3.connect(str(get_db_path()))
    try:
        row = conn.execute("SELECT MAX(date) FROM stock_prices").fetchone()
        return str(row[0])[:10]
    finally:
        conn.close()


def _scenario_config(strategy_cfg: Dict[str, Any], scenario_key: str) -> Dict[str, Any]:
    spec = CAPITAL_SCENARIOS[scenario_key]
    cfg = {k: v for k, v in strategy_cfg.items() if k in ALLOWED_BT_KEYS}
    cfg["initial_capital"] = float(spec["initial_capital"])
    cfg["monthly_contribution"] = float(spec["monthly_contribution"])
    return cfg


def _run_one(task: Tuple[str, str, Dict[str, Any], str, str, str, bool]) -> Dict[str, Any]:
    """Top-level worker for ProcessPoolExecutor."""
    strategy_id, scenario_key, scen_cfg, start_date, end_date, data_end, force = task
    if not force:
        existing_id = has_run(
            strategy_id=strategy_id,
            scenario=scenario_key,
            config=scen_cfg,
            data_end=data_end,
            start_date=start_date,
            end_date=end_date,
        )
        if existing_id is not None:
            return {
                "strategy_id": strategy_id,
                "scenario": scenario_key,
                "run_id": existing_id,
                "skipped": True,
            }

    result = run_backtest(
        start_date=start_date,
        end_date=end_date,
        **scen_cfg,
    )
    run_id = save_run(
        strategy_id=strategy_id,
        scenario=scenario_key,
        config=scen_cfg,
        result=result,
        data_end=data_end,
    )
    return {
        "strategy_id": strategy_id,
        "scenario": scenario_key,
        "run_id": run_id,
        "skipped": False,
        "final_nav": round(result.final_nav, 0),
        "sharpe": round(result.sharpe_ratio, 3),
        "trades": result.total_trades,
    }


def _execute_batch(
    strategy_ids: List[str],
    start_date: str,
    end_date: str,
    data_end: str,
    workers: int,
    force: bool,
) -> List[Dict[str, Any]]:
    tasks: List[Tuple[str, str, Dict[str, Any], str, str, str, bool]] = []
    for sid in strategy_ids:
        payload = load_strategy(sid)
        if payload is None:
            raise RuntimeError(f"Strategy not found in registry: {sid}")
        for scenario_key in CAPITAL_SCENARIOS:
            scen_cfg = _scenario_config(payload["config"], scenario_key)
            tasks.append((sid, scenario_key, scen_cfg, start_date, end_date, data_end, force))

    outcomes: List[Dict[str, Any]] = []
    if workers <= 1:
        for t in tasks:
            out = _run_one(t)
            tag = "SKIP" if out["skipped"] else "DONE"
            print(f"  [{tag}] {out['strategy_id']:28s} {out['scenario']:8s} run_id={out['run_id']}")
            outcomes.append(out)
        return outcomes

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, t): t for t in tasks}
        for fut in as_completed(futures):
            out = fut.result()
            tag = "SKIP" if out["skipped"] else "DONE"
            extra = "" if out["skipped"] else f" sharpe={out['sharpe']:+.2f} trades={out['trades']} nav={out['final_nav']:,.0f}"
            print(f"  [{tag}] {out['strategy_id']:28s} {out['scenario']:8s} run_id={out['run_id']}{extra}")
            outcomes.append(out)
    return outcomes


def _write_selected_combos(data_end: str) -> Dict[str, List[str]]:
    """Select top-3, top-5, and C5+best strictly from 2020-2024 in-sample solo Sharpe."""
    solo_runs = load_latest_runs(data_end=data_end, strategy_ids=SOLO_STRATEGY_IDS)
    # Rank solo strategies using 2020-2024 in-sample lump_10l Sharpe (tie-break: IS TWR CAGR)
    scored: List[Tuple[str, str, float, float, int]] = []
    for r in solo_runs:
        if r["scenario"] != "lump_10l":
            continue
        is_m = r["in_sample_metrics"]
        sig_list = r["config"].get("signal_types") or []
        if not sig_list:
            continue
        scored.append(
            (
                r["strategy_id"],
                sig_list[0],
                float(is_m.get("sharpe", 0.0)),
                float(is_m.get("twr_cagr_pct", 0.0)),
                int(is_m.get("trades", 0)),
            )
        )
    # Prefer strategies with >= 5 in-sample trades so degenerate 0-trade strategies stay bottom
    scored.sort(key=lambda x: (1 if x[4] >= 5 else 0, x[2], x[3]), reverse=True)
    if len(scored) < 5:
        raise RuntimeError(f"Expected >= 5 solo runs for selection, found {len(scored)}")

    top3_sigs = [x[1] for x in scored[:3]]
    top5_sigs = [x[1] for x in scored[:5]]
    best_sig = scored[0][1]

    c5 = load_strategy("default_c5")
    if c5 is None:
        raise RuntimeError("default_c5 not found in registry")
    c5_sigs = list(c5["config"]["signal_types"])
    c5_plus_sigs = c5_sigs + ([best_sig] if best_sig not in c5_sigs else [])

    now_iso = datetime.now().isoformat(timespec="seconds")
    base_cfg = {
        "bear_threshold": -0.05,
        "event_exit_mode": False,
        "holding_days": 30,
        "initial_capital": 1000000.0,
        "max_positions": 5,
        "profit_target_pct": None,
        "rebalance_frequency": 3,
        "regime_max_positions": {"bear": 2, "bull": 5, "neutral": 4},
        "regime_sector_limits": {"bear": 0.25, "bull": 0.5, "neutral": 0.35},
        "sector_limit": 0.35,
        "stop_loss_pct": 0.08,
        "trailing_stop_pct": 0.1,
        "use_regime_filter": True,
        "use_trailing_stop": True,
    }

    combos = [
        (
            "combo_top3_sharpe",
            "Combo: Top 3 Solo (IS Sharpe)",
            f"Top 3 NEPSE solo strategies selected strictly by 2020-2024 in-sample Sharpe: {', '.join(top3_sigs)}.",
            {**base_cfg, "signal_types": top3_sigs},
        ),
        (
            "combo_top5_sharpe",
            "Combo: Top 5 Solo (IS Sharpe)",
            f"Top 5 NEPSE solo strategies selected strictly by 2020-2024 in-sample Sharpe: {', '.join(top5_sigs)}.",
            {**base_cfg, "signal_types": top5_sigs},
        ),
        (
            "combo_c5_plus_best",
            f"Combo: C5 + Best New ({best_sig})",
            f"C5 Baseline signals plus top 2020-2024 in-sample new signal ({best_sig}).",
            {**c5["config"], "signal_types": c5_plus_sigs},
        ),
    ]

    for sid, name, desc, cfg in combos:
        payload = {
            "config": cfg,
            "created_at": now_iso,
            "description": desc,
            "editable": False,
            "execution_mode": "paper_runtime",
            "id": sid,
            "name": name,
            "notes": {
                "family": "nepse_combo",
                "selection_window": "2020-01-01..2024-12-31",
                "tradeable_only": True,
            },
            "ranking_overlay": {"mode": "baseline"},
            "runner_mode": "standard",
            "source": "builtin",
            "updated_at": now_iso,
        }
        out_path = BUILTIN_STRATEGY_DIR / f"{sid}.json"
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("\nSelected combinations (strictly from 2020-2024 in-sample Sharpe):")
    for rank, (sid, sig, sh, cagr, tr) in enumerate(scored, 1):
        print(f"  {rank}. {sid:28s} ({sig:20s}) IS Sharpe={sh:+.3f} IS CAGR={cagr:+.2f}% trades={tr}")
    return {
        "combo_top3_sharpe": top3_sigs,
        "combo_top5_sharpe": top5_sigs,
        "combo_c5_plus_best": c5_plus_sigs,
    }


def _fmt_pct(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    return f"{val:+.2f}%"


def _fmt_npr(val: float) -> str:
    return f"NPR {val:,.0f}"


def _safe_filename(name: str) -> str:
    return (
        name.replace("/", "-")
        .replace(":", " -")
        .replace("+", "Plus")
        .replace("  ", " ")
        .strip()
    )


def _generate_charts(
    runs_by_scenario: Dict[str, List[Dict[str, Any]]],
    charts_dir: Path,
) -> Dict[str, Path]:
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_paths: Dict[str, Path] = {}

    for scenario_key, spec in CAPITAL_SCENARIOS.items():
        rows = runs_by_scenario.get(scenario_key, [])
        if not rows:
            continue
        # Plot C5 + top 6 strategies by Full Sharpe
        ranked = sorted(rows, key=lambda r: float(r["metrics"].get("sharpe", 0.0)), reverse=True)
        picked: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for r in ranked:
            if r["strategy_id"] == "default_c5":
                picked.append(r)
                seen_ids.add(r["strategy_id"])
                break
        for r in ranked:
            if r["strategy_id"] not in seen_ids and len(picked) < 7:
                picked.append(r)
                seen_ids.add(r["strategy_id"])

        fig, ax = plt.subplots(figsize=(11, 5.5))
        for r in picked:
            nav_df = load_run_nav(r["run_id"])
            if nav_df.empty:
                continue
            strat = load_strategy(r["strategy_id"])
            label = (strat["name"] if strat else r["strategy_id"])
            sharpe = float(r["metrics"].get("sharpe", 0.0))
            is_c5 = r["strategy_id"] == "default_c5"
            ax.plot(
                nav_df["date"],
                nav_df["nav"] / 1000.0,
                label=f"{label} (Sharpe {sharpe:.2f})",
                linewidth=2.4 if is_c5 else 1.5,
                linestyle="--" if is_c5 else "-",
                alpha=0.95 if is_c5 else 0.85,
            )

        # Vertical line marking 2025-01-01 OOS split
        ax.axvline(pd.Timestamp("2025-01-01"), color="#666666", linestyle=":", linewidth=1.2, label="OOS Split (2025-01-01)")
        ax.set_yscale("log")
        ax.set_title(f"Account Value (NAV, Log Scale) — {spec['label']} ({scenario_key})")
        ax.set_xlabel("Date")
        ax.set_ylabel("Account Value (NPR Thousands, log)")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", fontsize=8.5, framealpha=0.9)
        fig.tight_layout()

        out_png = charts_dir / f"nav_{scenario_key}.png"
        fig.savefig(out_png, dpi=140)
        plt.close(fig)
        chart_paths[scenario_key] = out_png

    return chart_paths


def generate_vault_reports(
    *,
    all_strategy_ids: List[str],
    data_end: str,
    run_stamp: str,
    start_date: str,
) -> Tuple[List[Path], Path]:
    reports_root = ROOT / "nqt-vault" / "Backtest Reports"
    run_dir = reports_root / run_stamp
    charts_dir = run_dir / "charts"
    run_dir.mkdir(parents=True, exist_ok=True)
    run_date = run_stamp[:10]
    run_display = run_stamp.replace("_", " ")
    if len(run_stamp) == 15 and run_stamp[10] == "_":
        run_display = f"{run_stamp[:10]} {run_stamp[11:13]}:{run_stamp[13:15]}"

    runs = load_latest_runs(data_end=data_end, strategy_ids=all_strategy_ids)
    by_strat: Dict[str, Dict[str, Dict[str, Any]]] = {}
    by_scenario: Dict[str, List[Dict[str, Any]]] = {k: [] for k in CAPITAL_SCENARIOS}

    for r in runs:
        by_strat.setdefault(r["strategy_id"], {})[r["scenario"]] = r
        if r["scenario"] in by_scenario:
            by_scenario[r["scenario"]].append(r)

    per_run_paths: List[Path] = []
    tracker_rows: List[str] = []

    for sid in all_strategy_ids:
        strat = load_strategy(sid)
        name = strat["name"] if strat else sid
        desc = strat["description"] if strat else ""
        sigs = ", ".join(strat["config"].get("signal_types", [])) if strat else ""
        scen_map = by_strat.get(sid, {})
        if not scen_map:
            continue

        note_label = "C5 Baseline (NAV Sizing)" if sid == "default_c5" else _safe_filename(name)
        note_path = run_dir / f"{note_label}.md"
        note_wikilink = f"[[{run_stamp}/{note_label}|{note_label}]]"

        lines = [
            "---",
            f"title: {note_label} ({run_display})",
            "tags: [backtest, report, strategy]",
            "status: active",
            f"date: {run_date}",
            f"run_stamp: {run_stamp}",
            "---",
            "",
            f"# {name} ({run_display})",
            "",
            f"- **Strategy ID:** `{sid}`",
            f"- **Signals:** `{sigs}`",
            f"- **Description:** {desc}",
            f"- **Window:** `{start_date}` → `{data_end}` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..{data_end}`)",
            "- **Trade DB:** `data/backtests.db`",
            "",
            "## Scenario Summary",
            "",
            "| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]

        for sc_key, spec in CAPITAL_SCENARIOS.items():
            r = scen_map.get(sc_key)
            if not r:
                continue
            m = r["metrics"]
            oos = r["out_of_sample_metrics"]
            lines.append(
                f"| `{sc_key}` ({spec['label']}) | {r['run_id']} | {_fmt_npr(m['total_contributed'])} | "
                f"{_fmt_npr(m['final_nav'])} | {_fmt_pct(m['twr_total_return_pct'])} | "
                f"{_fmt_pct(m['twr_cagr_pct'])} | {_fmt_pct(m['xirr_pct'])} | "
                f"{m['sharpe']:.2f} | {_fmt_pct(m['max_drawdown_pct'])} | "
                f"{m['trades']} | {m['win_rate_pct']:.1f}% | {m['fees_pct_of_contributed']:.2f}% | "
                f"{_fmt_pct(oos['twr_cagr_pct'])} | {oos['sharpe']:.2f} |"
            )
            tracker_rows.append(
                f"| {run_display} | {note_wikilink} | `{sid}` | `{sc_key}` | "
                f"`{start_date}` → `{data_end}` | complete | {_fmt_pct(m['twr_total_return_pct'])} | "
                f"{_fmt_pct(m['twr_cagr_pct'])} | {_fmt_pct(m['xirr_pct'])} | {m['sharpe']:.2f} | "
                f"{_fmt_pct(m['max_drawdown_pct'])} | {m['trades']} |"
            )

        lines.extend(
            [
                "",
                "## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)",
                "",
                "| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for sc_key in CAPITAL_SCENARIOS:
            r = scen_map.get(sc_key)
            if not r:
                continue
            ism = r["in_sample_metrics"]
            oos = r["out_of_sample_metrics"]
            lines.append(
                f"| `{sc_key}` | {_fmt_pct(ism['twr_cagr_pct'])} | {ism['sharpe']:.2f} | "
                f"{_fmt_pct(ism['max_drawdown_pct'])} | {ism['trades']} | "
                f"{_fmt_pct(oos['twr_cagr_pct'])} | {oos['sharpe']:.2f} | "
                f"{_fmt_pct(oos['max_drawdown_pct'])} | {oos['trades']} |"
            )

        lines.extend(
            [
                "",
                f"Related: [[{run_stamp}/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].",
                "",
            ]
        )
        note_path.write_text("\n".join(lines), encoding="utf-8")
        per_run_paths.append(note_path)

    # Generate comparison charts inside the timestamped run folder
    chart_paths = _generate_charts(by_scenario, charts_dir)

    # Build Strategy Comparison report inside the timestamped run folder
    comp_path = run_dir / "Strategy Comparison.md"
    comp_wikilink = f"[[{run_stamp}/Strategy Comparison|{run_display} — Strategy Comparison]]"

    c5_by_scen = by_strat.get("default_c5", {})

    comp_lines = [
        "---",
        f"title: Strategy Comparison ({run_display})",
        "tags: [backtest, comparison, strategies, report]",
        "status: active",
        f"date: {run_date}",
        f"run_stamp: {run_stamp}",
        "---",
        "",
        f"# NEPSE Strategy Comparison ({run_display})",
        "",
        f"- **Run folder:** `nqt-vault/Backtest Reports/{run_stamp}/`",
        f"- **Window:** `{start_date}` → `{data_end}`",
        "- **Selection discipline:** Combination strategies (`combo_top3_sharpe`, `combo_top5_sharpe`, `combo_c5_plus_best`) were selected strictly from `2020-01-01..2024-12-31` solo Sharpe ratios. `2025-01-01` onward is reported separately as Out-of-Sample (OOS).",
        "- **Engine rules:** Equal-weight sizing from current account NAV (cash + MTM holdings), no NPR 10K floor, 10-share minimum lot preserved, small-account position caps, realistic NEPSE fees including NPR 25 DP charge.",
        "- **Trade persistence:** All runs, trades, daily NAV, and BS monthly deposits stored in `data/backtests.db`.",
        "",
        "> [!warning] Execution realism caveat (`ipo_momentum` and combos containing it)",
        "> Real NEPSE IPOs (e.g. `CGH`, `JBLB`, `MKCL`, `GMLI`, `NMIC`) frequently lock at the +10% upper circuit for 10–20 consecutive sessions with almost zero willing sellers. Because the base backtest engine fills T+1 open orders even on limit-locked sessions (`limit-locked days still fill`), `nepse_ipo_momentum` and combinations containing it (`combo_trend`, `combo_top3_sharpe`, `combo_top5_sharpe`, `combo_c5_plus_best`) overstate achievable live returns. Always inspect both the full ranking and the non-IPO strategies (`default_c5`, `nepse_book_closure_runup`, `nepse_lead_lag`, `nepse_calendar_festival`, `nepse_sector_rotation`).",
        "",
        "## Strategies Beating C5 Baseline",
        "",
    ]

    # Compute which strategies beat C5 on Sharpe across scenarios
    beat_all_full: List[str] = []
    beat_any_full: List[Tuple[str, List[str], List[str]]] = []
    for sid in all_strategy_ids:
        if sid == "default_c5":
            continue
        smap = by_strat.get(sid, {})
        full_wins: List[str] = []
        oos_wins: List[str] = []
        for sc_key in CAPITAL_SCENARIOS:
            r = smap.get(sc_key)
            c5r = c5_by_scen.get(sc_key)
            if not r or not c5r:
                continue
            if float(r["metrics"]["sharpe"]) > float(c5r["metrics"]["sharpe"]) and int(r["metrics"]["trades"]) >= 10:
                full_wins.append(sc_key)
            if float(r["out_of_sample_metrics"]["sharpe"]) > float(c5r["out_of_sample_metrics"]["sharpe"]):
                oos_wins.append(sc_key)
        if len(full_wins) == len(CAPITAL_SCENARIOS):
            beat_all_full.append(sid)
        if full_wins or oos_wins:
            beat_any_full.append((sid, full_wins, oos_wins))

    if beat_all_full:
        comp_lines.append("**Consistently beat C5 Sharpe across all 3 capital scenarios (full window, >= 10 trades):**")
        for sid in beat_all_full:
            strat = load_strategy(sid)
            comp_lines.append(f"- `{sid}` ({strat['name'] if strat else sid})")
    else:
        comp_lines.append("**Consistently beat C5 Sharpe across all 3 capital scenarios (full window, >= 10 trades):** None.")

    comp_lines.extend(
        [
            "",
            "| Strategy | Beats C5 Full-Window Sharpe | Beats C5 2025–2026 OOS Sharpe |",
            "| --- | --- | --- |",
        ]
    )
    for sid, fw, ow in sorted(beat_any_full, key=lambda x: (len(x[1]), len(x[2])), reverse=True):
        strat = load_strategy(sid)
        label = f"`{sid}` ({strat['name'] if strat else sid})"
        comp_lines.append(
            f"| {label} | {', '.join(fw) if fw else '—'} | {', '.join(ow) if ow else '—'} |"
        )

    for sc_key, spec in CAPITAL_SCENARIOS.items():
        rows = sorted(
            by_scenario.get(sc_key, []),
            key=lambda r: float(r["metrics"].get("sharpe", 0.0)),
            reverse=True,
        )
        comp_lines.extend(
            [
                "",
                f"## Scenario: `{sc_key}` — {spec['label']}",
                "",
            ]
        )
        if sc_key in chart_paths:
            rel_chart = f"charts/{chart_paths[sc_key].name}"
            comp_lines.append(f"![{spec['label']} Account Value]({rel_chart})")
            comp_lines.append("")

        comp_lines.extend(
            [
                "| Rank | Strategy | Final NAV | Contributed | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |",
                "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for rank, r in enumerate(rows, 1):
            sid = r["strategy_id"]
            strat = load_strategy(sid)
            name = strat["name"] if strat else sid
            note_label = "C5 Baseline (NAV Sizing)" if sid == "default_c5" else _safe_filename(name)
            note_link = f"[[{run_stamp}/{note_label}|{name}]]"
            if sid == "default_c5":
                note_link = f"**{note_link}**"
            m = r["metrics"]
            oos = r["out_of_sample_metrics"]
            comp_lines.append(
                f"| {rank} | {note_link} | {_fmt_npr(m['final_nav'])} | {_fmt_npr(m['total_contributed'])} | "
                f"{_fmt_pct(m['twr_cagr_pct'])} | {_fmt_pct(m['xirr_pct'])} | "
                f"{m['sharpe']:.2f} | {_fmt_pct(m['max_drawdown_pct'])} | "
                f"{m['trades']} | {m['fees_pct_of_contributed']:.2f}% | "
                f"{_fmt_pct(oos['twr_cagr_pct'])} | {oos['sharpe']:.2f} |"
            )

    comp_lines.extend(
        [
            "",
            "Related: [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]], [[Baseline Backtest]], [[Decision Log]].",
            "",
        ]
    )
    comp_path.write_text("\n".join(comp_lines), encoding="utf-8")

    # Discover all timestamped suite folders (newest first) for the top-level MOC
    suite_folders = sorted(
        [p.name for p in reports_root.iterdir() if p.is_dir() and (p / "Strategy Comparison.md").exists()],
        reverse=True,
    )
    suite_list_lines = [
        f"- [[{folder}/Strategy Comparison|{folder.replace('_', ' ')} — Strategy Comparison]] (`{folder}/`)"
        for folder in suite_folders
    ]

    # Update Backtest Reports.md MOC
    index_path = reports_root / "Backtest Reports.md"
    index_lines = [
        "---",
        "title: Backtest Reports",
        "tags: [moc, validation, backtest, reports]",
        "status: active",
        "---",
        "",
        "# Backtest Reports",
        "",
        "Dated paper-backtest run logs grouped by run timestamp (`YYYY-MM-DD_HHMM/`) so reports and charts stay tidy.",
        "",
        "- **Folder layout:** `nqt-vault/Backtest Reports/YYYY-MM-DD_HHMM/` (`Strategy Comparison.md`, `<Strategy>.md`, `charts/nav_<scenario>.png`)",
        "- **Standard scenarios:** Every backtest runs all 3 `CAPITAL_SCENARIOS` (`lump_10l`, `lump_1l`, `sip_5k`).",
        "- **Trade store (gitignored):** `data/backtests.db` (`runs`, `trades`, `daily_nav`, `contributions`)",
        f"- **Latest comparison report:** {comp_wikilink}",
        "- **Methodology & reproduction:** [[Baseline Backtest]] · [[Backtesting Process]] · [[Strategy Catalog]] · [[External Market Data Sources]] · [[Validation Suite]]",
        "",
        "## Suite Runs (Newest First)",
        "",
        *suite_list_lines,
        "",
        f"## Latest Run Tracker (`{run_display}`)",
        "",
        "| Run | Report | Strategy | Scenario | Window | Status | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *tracker_rows,
        "| 2026-11-20 (legacy) | [[2026-11-20 - C5 Baseline]] | `default_c5` | `lump_10l` *(fixed-cap sizing)* | `2020-01-01` → `2026-11-19` | complete | +121.09% | +12.21% | — | 1.07 | -26.14% | 209 |",
        "| 2026-11-20 (legacy) | [[2026-11-20 - C5 Baseline (Partial)]] | `default_c5` | `lump_10l` *(fixed-cap)* | `2020-01-01` → `2025-02-10` | partial | +109.45% | +15.56% | — | — | -22.07%* | 160 |",
        "",
        "\\*Checkpoint floor from 50-day log intervals; true daily drawdown is at least this magnitude.",
        "",
        "Related: [[00 - Index]], [[Baseline Backtest]], [[Backtesting Process]], [[Strategy Catalog]], [[Signal Engine]], [[Strategy Registry]], [[Change Log]].",
        "",
    ]
    index_path.write_text("\n".join(index_lines), encoding="utf-8")

    return per_run_paths, comp_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run NEPSE strategy suite across all 3 capital scenarios")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None, help="Default: MAX(date) in stock_prices")
    parser.add_argument("--workers", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 1)))
    parser.add_argument("--force", action="store_true", help="Re-run even if matching run exists in data/backtests.db")
    parser.add_argument("--reports-only", action="store_true", help="Skip backtests and regenerate vault reports from DB")
    parser.add_argument("--run-stamp", default=None, help="Folder timestamp YYYY-MM-DD_HHMM (default: current local time)")
    args = parser.parse_args(argv)

    data_end = _db_max_date()
    end_date = args.end or data_end
    run_stamp = args.run_stamp or datetime.now().strftime("%Y-%m-%d_%H%M")

    print(f"NEPSE Strategy Suite | window {args.start} -> {end_date} | data_end={data_end} | workers={args.workers} | folder={run_stamp}")

    if not args.reports_only:
        print("\n=== Phase 1: 9 Solo Strategies x 3 Capital Scenarios (27 runs) ===")
        _execute_batch(SOLO_STRATEGY_IDS, args.start, end_date, data_end, args.workers, args.force)

        print("\n=== Phase 2: Select Combinations from 2020-2024 In-Sample Sharpe ===")
        _write_selected_combos(data_end)

        print("\n=== Phase 3: 5 Combinations + C5 Baseline Re-Run x 3 Capital Scenarios (18 runs) ===")
        phase3_ids = FIXED_COMBO_IDS + SELECTED_COMBO_IDS + ["default_c5"]
        _execute_batch(phase3_ids, args.start, end_date, data_end, args.workers, args.force)

    print("\n=== Phase 4: Generate Vault Reports & Account-Value Charts ===")
    all_ids = ["default_c5"] + SOLO_STRATEGY_IDS + FIXED_COMBO_IDS + SELECTED_COMBO_IDS
    per_run_paths, comp_path = generate_vault_reports(
        all_strategy_ids=all_ids,
        data_end=data_end,
        run_stamp=run_stamp,
        start_date=args.start,
    )
    print(f"Wrote {len(per_run_paths)} per-strategy reports and comparison report: {comp_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
