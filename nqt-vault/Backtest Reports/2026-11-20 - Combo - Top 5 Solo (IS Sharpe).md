---
title: 2026-11-20 - Combo - Top 5 Solo (IS Sharpe)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
---

# Combo: Top 5 Solo (IS Sharpe) (2026-11-20)

- **Strategy ID:** `combo_top5_sharpe`
- **Signals:** `ipo_momentum, lead_lag, sector_rotation, calendar_festival, book_closure_runup`
- **Description:** Top 5 NEPSE solo strategies selected strictly by 2020-2024 in-sample Sharpe: ipo_momentum, lead_lag, sector_rotation, calendar_festival, book_closure_runup.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 37 | NPR 1,000,000 | NPR 19,857,234 | +1885.72% | +54.33% | +54.33% | 1.75 | -36.95% | 341 | 37.5% | 308.05% | +76.97% | 2.44 |
| `lump_1l` (1L Lump Sum) | 38 | NPR 100,000 | NPR 1,957,361 | +1857.36% | +54.00% | +54.00% | 1.73 | -40.06% | 333 | 36.6% | 364.33% | +75.26% | 2.40 |
| `sip_5k` (5K + 5K/BS Month) | 39 | NPR 415,000 | NPR 2,353,370 | +1819.72% | +53.57% | +51.01% | 1.63 | -41.83% | 303 | 38.0% | 83.81% | +77.03% | 2.45 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +46.63% | 1.53 | -36.95% | 261 | +76.97% | 2.44 | -22.51% | 80 |
| `lump_1l` | +46.74% | 1.52 | -40.06% | 253 | +75.26% | 2.40 | -22.89% | 80 |
| `sip_5k` | +45.62% | 1.39 | -41.83% | 224 | +77.03% | 2.45 | -22.82% | 79 |

Related: [[2026-11-20 - Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
