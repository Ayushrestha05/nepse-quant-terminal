---
title: NEPSE IPO Listing Momentum (2026-11-20 11:08)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1108
---

# NEPSE IPO Listing Momentum (2026-11-20 11:08)

- **Strategy ID:** `nepse_ipo_momentum`
- **Signals:** `ipo_momentum`
- **Description:** Post-IPO listing discovery momentum (first trading day > 2017, excludes merger listings).
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 7 | NPR 1,000,000 | NPR 244,021,312 | +24302.13% | +122.14% | +122.14% | 3.19 | -21.71% | 201 | 48.3% | 928.20% | +335.63% | 4.24 |
| `lump_1l` (1L Lump Sum) | 8 | NPR 100,000 | NPR 24,855,612 | +24755.61% | +122.73% | +122.73% | 3.15 | -21.87% | 199 | 47.2% | 1112.75% | +332.25% | 4.22 |
| `sip_5k` (5K + 5K/BS Month) | 9 | NPR 415,000 | NPR 24,977,773 | +24702.98% | +122.66% | +134.07% | 3.06 | -21.87% | 195 | 46.2% | 263.71% | +332.24% | 4.22 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +72.49% | 2.72 | -20.15% | 149 | +335.63% | 4.24 | -21.71% | 52 |
| `lump_1l` | +73.64% | 2.65 | -20.43% | 147 | +332.25% | 4.22 | -21.87% | 52 |
| `sip_5k` | +73.56% | 2.50 | -20.42% | 143 | +332.24% | 4.22 | -21.87% | 52 |

Related: [[2026-11-20_1108/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
