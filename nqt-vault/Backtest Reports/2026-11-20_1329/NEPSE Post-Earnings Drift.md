---
title: NEPSE Post-Earnings Drift (2026-11-20 13:29)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1329
---

# NEPSE Post-Earnings Drift (2026-11-20 13:29)

- **Strategy ID:** `nepse_earnings_drift`
- **Signals:** `earnings_drift`
- **Description:** Post-earnings announcement drift (PEAD) on strong quarterly net-profit / EPS growth with volume confirmation.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 17 | NPR 1,000,000 | NPR 798,427 | -20.16% | -3.22% | -3.22% | -0.14 | -53.31% | 136 | 33.1% | 23.65% | -6.13% | -0.55 |
| `lump_1l` (1L Lump Sum) | 16 | NPR 100,000 | NPR 65,917 | -34.08% | -5.87% | -5.87% | -0.26 | -60.27% | 104 | 33.7% | 32.33% | -11.69% | -1.08 |
| `sip_5k` (5K + 5K/BS Month) | 18 | NPR 415,000 | NPR 335,007 | -27.88% | -4.63% | -6.28% | -0.14 | -58.63% | 115 | 29.6% | 11.10% | -5.93% | -0.54 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | -2.10% | -0.05 | -53.31% | 108 | -6.13% | -0.55 | -18.58% | 28 |
| `lump_1l` | -3.59% | -0.09 | -59.47% | 84 | -11.69% | -1.08 | -31.61% | 20 |
| `sip_5k` | -4.14% | -0.08 | -58.63% | 88 | -5.93% | -0.54 | -17.95% | 27 |

Related: [[2026-11-20_1329/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
