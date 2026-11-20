---
title: Baseline Backtest
tags: [validation, baseline, paper]
status: partial
---

# Baseline Backtest

Paper simulation of the built-in **C5** strategy (`data/strategy_registry/builtin/default_c5.json`) vs NEPSE buy-and-hold.

## How to reproduce

```bash
# clean env if Cursor AppImage pollutes LD_LIBRARY_PATH — use project .venv
.venv/bin/python setup_data.py
.venv/bin/python setup_data.py --scrape --days 230   # top-up after bundled cutoff
.venv/bin/python scripts/validation/run_baseline.py
```

Outputs (gitignored): `data/runtime/baselines/<run_date>/` — `summary.txt`, `metrics.json`, `trades.csv`, `nav.csv`.

Cross-check cache: `data/runtime/crosscheck/`.

## Window and rules

- **Target window:** `2020-01-01` → `2026-11-19` (1,557 trading days; 405 symbols; 504,616 price rows)
- **Partial run reached:** `2020-01-01` → `2025-02-10` (day **1,150 / 1,557**, 73.9%; stopped early at ~4h15m before summary export)
- **Prices:** adjusted (Merolagani `isAdjust=1`)
- **Exclude:** symbols where menaceXnadin overlap has >5% of days with close mismatch >1%
- **Engine:** `run_backtest(..., exclude_symbols=…)` fees + stops + regime filter; **no slippage**

## Partial Metrics (`2020-01-01` → `2025-02-10`, 5.11y)

Derived from 50-day NAV checkpoints in the run log (full trade-level stats require a completed run).

| Metric | C5 (partial, 50-day checkpoints) | NEPSE buy-and-hold (same window) | NEPSE buy-and-hold (to `2026-04-15`) |
| --- | --- | --- | --- |
| Start → End NAV / Close | NPR 1,000,000 → 2,094,509 | 1,169.50 → 2,677.32 | 1,169.50 → 2,833.60 |
| Total return | **+109.45%** | +128.93% | +142.29% |
| Annualized (CAGR) | **+15.56%** | +17.59% | +15.12% |
| Max drawdown | **-22.07%** *(checkpoint floor; true daily ≥ this)* | -43.25% | -43.25% |
| Trades (to day 1,150) | **160** | — | — |
| Sharpe / win rate / PF | Pending full completion | — | — |

- **Excluded symbols (menaceXnadin cross-check, 21 symbols):** `0` (`none`).

## Issues found during run

1. **NEPSE index stops at `2026-04-15`** (`stock_prices WHERE symbol='NEPSE'` max date = `2026-04-15`, while 352 stocks extend to `2026-11-19`). Must top up `NEPSE` before trusting regime-filter or benchmark numbers post-`2026-04-15`.
2. **Runtime bottleneck:** ~11 min per 50 trading days (~5.5–6h for 1,557 days) in `simple_backtest.py` (single-threaded daily signal scan). Adding checkpoint/resume or optimizing per-day scan is needed before iterating on baselines.

## Caveats

- Partial run stopped at day 1,150/1,557; no `metrics.json` / `trades.csv` / `nav.csv` written yet.
- In-sample relative to C5 parameter history (see README disclaimer).
- No slippage; limit-locked days still fill.
- Survivorship bias: delisted stocks missing from the universe.
- Corporate actions only refreshed for top 20 symbols (prices are already `isAdjust=1`).

## Data sources & reports

- Data sources: [[External Market Data Sources]]
- Run reports: [[Backtest Reports]] (latest: [[2026-11-20 - C5 Baseline (Partial)]])

Related: [[Validation Suite]], [[Signal Engine]], [[News Sentiment Pipeline]], [[Change Log]].
