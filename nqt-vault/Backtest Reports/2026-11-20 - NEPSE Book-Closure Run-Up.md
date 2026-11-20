---
title: 2026-11-20 - NEPSE Book-Closure Run-Up
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
---

# NEPSE Book-Closure Run-Up (2026-11-20)

- **Strategy ID:** `nepse_book_closure_runup`
- **Signals:** `book_closure_runup`
- **Description:** Book-closure run-up before cash/bonus dividends (3-15d statutory notice window, exits T-1 before bookclose).
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 3 | NPR 1,000,000 | NPR 1,262,916 | +26.29% | +3.45% | +3.45% | 0.61 | -10.23% | 84 | 52.4% | 16.50% | +1.76% | 0.57 |
| `lump_1l` (1L Lump Sum) | 6 | NPR 100,000 | NPR 129,596 | +29.60% | +3.84% | +3.84% | 0.58 | -13.13% | 83 | 53.0% | 26.48% | +1.72% | 0.45 |
| `sip_5k` (5K + 5K/BS Month) | 2 | NPR 415,000 | NPR 456,522 | +28.95% | +3.76% | +2.77% | 0.60 | -10.36% | 82 | 52.4% | 9.21% | +1.66% | 0.54 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +4.02% | 0.63 | -10.23% | 67 | +1.76% | 0.57 | -2.10% | 17 |
| `lump_1l` | +4.56% | 0.61 | -13.13% | 66 | +1.72% | 0.45 | -2.61% | 17 |
| `sip_5k` | +4.49% | 0.64 | -10.36% | 65 | +1.66% | 0.54 | -2.08% | 17 |

Related: [[2026-11-20 - Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
