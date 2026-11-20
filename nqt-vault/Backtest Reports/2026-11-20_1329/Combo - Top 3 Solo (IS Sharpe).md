---
title: Combo - Top 3 Solo (IS Sharpe) (2026-11-20 13:29)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1329
---

# Combo: Top 3 Solo (IS Sharpe) (2026-11-20 13:29)

- **Strategy ID:** `combo_top3_sharpe`
- **Signals:** `ipo_momentum, lead_lag, sector_rotation`
- **Description:** Top 3 NEPSE solo strategies selected strictly by 2020-2024 in-sample Sharpe: ipo_momentum, lead_lag, sector_rotation.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 34 | NPR 1,000,000 | NPR 20,877,784 | +1987.78% | +55.45% | +55.45% | 1.76 | -36.43% | 330 | 38.5% | 271.99% | +97.33% | 2.71 |
| `lump_1l` (1L Lump Sum) | 36 | NPR 100,000 | NPR 1,937,775 | +1837.77% | +53.78% | +53.78% | 1.71 | -39.83% | 317 | 38.5% | 310.79% | +94.84% | 2.66 |
| `sip_5k` (5K + 5K/BS Month) | 35 | NPR 415,000 | NPR 2,256,592 | +1714.42% | +52.32% | +49.72% | 1.61 | -44.41% | 291 | 37.5% | 70.37% | +97.11% | 2.71 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +42.14% | 1.43 | -36.43% | 251 | +97.33% | 2.71 | -18.29% | 79 |
| `lump_1l` | +40.71% | 1.37 | -39.83% | 239 | +94.84% | 2.66 | -18.70% | 78 |
| `sip_5k` | +38.27% | 1.25 | -44.41% | 213 | +97.11% | 2.71 | -16.99% | 78 |

Related: [[2026-11-20_1329/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
