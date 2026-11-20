---
title: NEPSE Calendar & Festival Effects (2026-11-20 11:08)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1108
---

# NEPSE Calendar & Festival Effects (2026-11-20 11:08)

- **Strategy ID:** `nepse_calendar_festival`
- **Signals:** `calendar_festival`
- **Description:** Nepali calendar liquidity effects: Ashad fiscal year-end rebound and Dashain/Tihar remittance flows.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 20 | NPR 1,000,000 | NPR 1,506,808 | +50.68% | +6.13% | +6.13% | 0.60 | -20.17% | 72 | 50.0% | 16.94% | -0.64% | -0.05 |
| `lump_1l` (1L Lump Sum) | 21 | NPR 100,000 | NPR 136,020 | +36.02% | +4.57% | +4.57% | 0.43 | -24.84% | 65 | 49.2% | 22.28% | -0.98% | -0.06 |
| `sip_5k` (5K + 5K/BS Month) | 19 | NPR 415,000 | NPR 435,334 | +27.99% | +3.65% | +1.39% | 0.36 | -24.56% | 64 | 45.3% | 7.71% | -0.75% | -0.07 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +8.80% | 0.77 | -20.17% | 55 | -0.64% | -0.05 | -10.40% | 17 |
| `lump_1l` | +6.74% | 0.57 | -24.84% | 49 | -0.98% | -0.06 | -12.57% | 16 |
| `sip_5k` | +5.35% | 0.46 | -24.56% | 47 | -0.75% | -0.07 | -10.42% | 17 |

Related: [[2026-11-20_1108/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
