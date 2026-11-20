---
title: NEPSE Ex-Date Gap Rebound (2026-11-20 13:29)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1329
---

# NEPSE Ex-Date Gap Rebound (2026-11-20 13:29)

- **Strategy ID:** `nepse_ex_date_gap`
- **Signals:** `ex_date_gap`
- **Description:** Ex-date gap rebound on bonus and right-share price adjustments.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 4 | NPR 1,000,000 | NPR 907,108 | -9.29% | -1.41% | -1.41% | -0.25 | -27.62% | 47 | 36.2% | 7.46% | +1.74% | 0.42 |
| `lump_1l` (1L Lump Sum) | 5 | NPR 100,000 | NPR 84,986 | -15.01% | -2.33% | -2.33% | -0.27 | -38.40% | 44 | 38.6% | 13.27% | +2.52% | 0.40 |
| `sip_5k` (5K + 5K/BS Month) | 1 | NPR 415,000 | NPR 399,573 | -17.00% | -2.67% | -1.11% | -0.43 | -35.18% | 44 | 31.8% | 4.49% | +1.61% | 0.40 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | -2.54% | -0.46 | -27.62% | 34 | +1.74% | 0.42 | -5.01% | 13 |
| `lump_1l` | -4.07% | -0.48 | -38.40% | 32 | +2.52% | 0.40 | -8.33% | 12 |
| `sip_5k` | -4.21% | -0.64 | -35.18% | 31 | +1.61% | 0.40 | -4.98% | 13 |

Related: [[2026-11-20_1329/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
