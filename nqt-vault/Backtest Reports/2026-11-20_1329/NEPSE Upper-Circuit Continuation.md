---
title: NEPSE Upper-Circuit Continuation (2026-11-20 13:29)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1329
---

# NEPSE Upper-Circuit Continuation (2026-11-20 13:29)

- **Strategy ID:** `nepse_circuit_continuation`
- **Signals:** `circuit_continuation`
- **Description:** Upper-circuit (+8.5%+) high-volume breakout continuation on NEPSE.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 14 | NPR 1,000,000 | NPR 568,479 | -43.15% | -7.87% | -7.87% | -0.28 | -65.40% | 395 | 34.2% | 71.71% | -39.66% | -2.83 |
| `lump_1l` (1L Lump Sum) | 15 | NPR 100,000 | NPR 20,663 | -79.34% | -20.46% | -20.46% | -0.71 | -86.04% | 326 | 29.8% | 94.23% | -56.33% | -2.76 |
| `sip_5k` (5K + 5K/BS Month) | 13 | NPR 415,000 | NPR 213,372 | -60.80% | -12.71% | -19.93% | -0.45 | -67.79% | 322 | 30.7% | 34.83% | -39.70% | -2.79 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +6.92% | 0.42 | -42.29% | 293 | -39.66% | -2.83 | -65.40% | 102 |
| `lump_1l` | -0.41% | 0.12 | -46.14% | 240 | -56.33% | -2.76 | -81.30% | 86 |
| `sip_5k` | -0.71% | 0.11 | -48.33% | 222 | -39.70% | -2.79 | -65.31% | 100 |

Related: [[2026-11-20_1329/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
