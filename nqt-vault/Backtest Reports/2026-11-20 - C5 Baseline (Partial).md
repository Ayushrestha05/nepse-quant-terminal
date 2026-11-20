---
title: 2026-11-20 - C5 Baseline (Partial)
tags: [backtest, report, c5, baseline, partial]
date: 2026-11-20
strategy: default_c5
status: partial
---

# 2026-11-20 — C5 Paper Baseline (Partial)

Back to [[Backtest Reports]] · Method: [[Baseline Backtest]] · Data: [[External Market Data Sources]].

## Run Summary

- **Strategy:** `default_c5` (`data/strategy_registry/builtin/default_c5.json`)
- **Command:** `scripts/validation/run_baseline.py --force`
- **Target window:** `2020-01-01` → `2026-11-19` (1,557 trading days)
- **Reached:** `2020-01-01` → `2025-02-10` (**1,150 / 1,557** days, 73.9%; stopped early after ~4h 15m)
- **Artifacts:** None written to `data/runtime/baselines/2026-11-20/` (export runs on completion); numbers below come from 50-day NAV checkpoints in `/tmp/nqt_baseline.log` and direct DB queries.

## Dataset & Cross-Check

- **`stock_prices`:** `504,616` rows, `405` symbols, `2015-12-03` → `2026-11-19` (`352` symbols topped up past `2026-04-15` via Merolagani `isAdjust=1`)
- **Supporting tables:** `quarterly_earnings` = `8,535`, `corporate_actions` = `589`, `fundamentals` = `329`, `financial_reports` = `166`
- **menaceXnadin cross-check (20 liquid + NEPSE):** **0 excluded** (`none` exceeded >5% of days with >1% close mismatch); cached in `data/runtime/crosscheck/` (21 files)

## Performance (`2020-01-01` → `2025-02-10`, 5.11y)

| Metric | C5 (50-day checkpoints) | NEPSE B&H (same window) | NEPSE B&H (to `2026-04-15`) |
| --- | ---: | ---: | ---: |
| Start → End | NPR 1,000,000 → 2,094,509 | 1,169.50 → 2,677.32 | 1,169.50 → 2,833.60 |
| Total return | **+109.45%** | +128.93% | +142.29% |
| Annualized (CAGR) | **+15.56%** | +17.59% | +15.12% |
| Max drawdown | **-22.07%** *(checkpoint floor)* | -43.25% | -43.25% |
| Trades | **160** | — | — |
| Sharpe / win rate / PF | Pending full run | — | — |

## Equity Checkpoints

| Day | Approx Phase | Trades | NAV (NPR) |
| ---: | --- | ---: | ---: |
| 0 | `2020-01-01` start | 0 | 1,000,000 |
| 150 | 2020–21 bull | 25 | 1,472,612 |
| 300 | 2021 expansion | 49 | 2,036,984 |
| 450 | `2022-02-08` peak | 68 | **2,154,692** |
| 600 | 2022–23 bear | 87 | 1,865,997 |
| 850 | `2023-10-11` trough (-22.1% DD) | 116 | **1,679,133** |
| 1,050 | 2024 rebound | 143 | 2,080,419 |
| 1,150 | `2025-02-10` stop | 160 | **2,094,509** |

## Findings & Action Items

1. **`NEPSE` index cutoff at `2026-04-15`:** `stock_prices WHERE symbol='NEPSE'` ends on `2026-04-15` while 352 stocks run through `2026-11-19`. Top up `NEPSE` before relying on post-April 2026 regime filtering or benchmark comparisons.
2. **Backtest speed bottleneck:** ~11 min per 50 trading days (~5.5–6h for 1,557 days) in `backend/backtesting/simple_backtest.py`. Profile/optimize daily signal scan or add checkpointing before re-running full baselines.

## Caveats

- Partial run; no trade-level CSV or Sharpe/win-rate export.
- In-sample relative to C5 parameter history; no slippage; limit-locked days still fill; survivorship bias (delisted stocks absent).

Related: [[Backtest Reports]], [[Baseline Backtest]], [[Validation Suite]], [[Signal Engine]], [[Change Log]].
