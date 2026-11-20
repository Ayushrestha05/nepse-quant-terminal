---
title: NEPSE NRB Monetary Policy (2026-11-20 11:08)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1108
---

# NEPSE NRB Monetary Policy (2026-11-20 11:08)

- **Strategy ID:** `nepse_nrb_policy`
- **Signals:** `nrb_policy`
- **Description:** Post-NRB Monetary Policy follow-through in rate-sensitive BFI sectors.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 22 | NPR 1,000,000 | NPR 676,447 | -32.36% | -5.52% | -5.52% | -0.85 | -32.36% | 34 | 14.7% | 4.81% | -2.99% | -0.48 |
| `lump_1l` (1L Lump Sum) | 24 | NPR 100,000 | NPR 64,602 | -35.40% | -6.15% | -6.15% | -0.79 | -35.40% | 23 | 17.4% | 6.58% | -2.30% | -0.23 |
| `sip_5k` (5K + 5K/BS Month) | 23 | NPR 415,000 | NPR 343,594 | -34.47% | -5.95% | -5.53% | -0.89 | -34.89% | 26 | 15.4% | 2.79% | -3.03% | -0.49 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | -6.46% | -0.98 | -28.38% | 26 | -2.99% | -0.48 | -15.39% | 8 |
| `lump_1l` | -7.56% | -1.04 | -32.51% | 17 | -2.30% | -0.23 | -19.52% | 6 |
| `sip_5k` | -7.03% | -1.03 | -31.07% | 18 | -3.03% | -0.49 | -15.29% | 8 |

Related: [[2026-11-20_1108/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
