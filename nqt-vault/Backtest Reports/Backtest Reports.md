---
title: Backtest Reports
tags: [moc, validation, backtest, reports]
status: active
---

# Backtest Reports

Dated paper-backtest run logs for comparing strategy versions, data snapshots, and parameter changes over time.

- **Naming:** `YYYY-MM-DD - <Strategy> <Label>.md`
- **Artifacts (gitignored):** `data/runtime/baselines/<run_date>/` (`summary.txt`, `metrics.json`, `trades.csv`, `nav.csv`)
- **Methodology & reproduction:** [[Baseline Backtest]] · [[Backtesting Process]] · [[External Market Data Sources]] · [[Validation Suite]]

## Run Tracker

| Date | Report | Strategy | Window | Status | Total Return | CAGR | Sharpe | Max DD | Trades | NEPSE B&H |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-11-20 | [[2026-11-20 - C5 Baseline]] | `default_c5` | `2020-01-01` → `2026-11-19` *(1,557d, 4m 14s)* | complete | +121.09% | +12.21% | 1.07 | -26.14% | 209 | +142.29% (-43.25% DD, to `2026-04-15`) |
| 2026-11-20 | [[2026-11-20 - C5 Baseline (Partial)]] | `default_c5` | `2020-01-01` → `2025-02-10` *(1,150/1,557d)* | partial | +109.45% | +15.56% | — | -22.07%* | 160 | +128.93% (-43.25% DD) |

\*Checkpoint floor from 50-day log intervals; true daily drawdown is at least this magnitude.

Related: [[00 - Index]], [[Baseline Backtest]], [[Backtesting Process]], [[Signal Engine]], [[Strategy Registry]], [[Change Log]].
