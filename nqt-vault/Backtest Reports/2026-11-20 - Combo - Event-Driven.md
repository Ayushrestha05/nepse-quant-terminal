---
title: 2026-11-20 - Combo - Event-Driven
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
---

# Combo: Event-Driven (2026-11-20)

- **Strategy ID:** `combo_event_driven`
- **Signals:** `book_closure_runup, ex_date_gap, earnings_drift`
- **Description:** Event-driven NEPSE combo: Book-Closure Run-Up + Ex-Date Gap Rebound + Post-Earnings Drift.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 29 | NPR 1,000,000 | NPR 760,644 | -23.94% | -3.89% | -3.89% | -0.18 | -59.67% | 223 | 39.5% | 41.75% | -9.27% | -1.11 |
| `lump_1l` (1L Lump Sum) | 31 | NPR 100,000 | NPR 66,487 | -33.51% | -5.75% | -5.75% | -0.23 | -66.72% | 194 | 40.2% | 64.38% | -16.36% | -1.43 |
| `sip_5k` (5K + 5K/BS Month) | 28 | NPR 415,000 | NPR 313,720 | -28.58% | -4.77% | -8.23% | -0.22 | -63.40% | 197 | 36.5% | 18.88% | -9.62% | -1.16 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | -1.84% | -0.02 | -57.28% | 178 | -9.27% | -1.11 | -24.81% | 45 |
| `lump_1l` | -1.50% | 0.03 | -64.95% | 153 | -16.36% | -1.43 | -36.99% | 41 |
| `sip_5k` | -2.92% | -0.07 | -62.85% | 152 | -9.62% | -1.16 | -25.09% | 45 |

Related: [[2026-11-20 - Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
