---
title: Combo - C5 Plus Best New (ipo_momentum) (2026-11-20 13:29)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1329
---

# Combo: C5 + Best New (ipo_momentum) (2026-11-20 13:29)

- **Strategy ID:** `combo_c5_plus_best`
- **Signals:** `volume, quality, low_vol, mean_reversion, quarterly_fundamental, xsec_momentum, ipo_momentum`
- **Description:** C5 Baseline signals plus top 2020-2024 in-sample new signal (ipo_momentum).
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 40 | NPR 1,000,000 | NPR 38,996,430 | +3799.64% | +70.21% | +70.21% | 2.38 | -39.70% | 232 | 43.1% | 300.15% | +135.86% | 3.36 |
| `lump_1l` (1L Lump Sum) | 41 | NPR 100,000 | NPR 2,317,084 | +2217.08% | +57.82% | +57.82% | 2.02 | -40.38% | 232 | 40.9% | 233.73% | +133.26% | 3.32 |
| `sip_5k` (5K + 5K/BS Month) | 43 | NPR 415,000 | NPR 2,872,919 | +1600.44% | +50.89% | +57.21% | 1.82 | -38.61% | 211 | 37.9% | 57.81% | +133.20% | 3.32 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +50.59% | 1.96 | -39.70% | 172 | +135.86% | 3.36 | -24.22% | 60 |
| `lump_1l` | +36.28% | 1.46 | -40.38% | 172 | +133.26% | 3.32 | -24.55% | 60 |
| `sip_5k` | +28.12% | 1.18 | -38.61% | 151 | +133.20% | 3.32 | -24.46% | 60 |

Related: [[2026-11-20_1329/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
