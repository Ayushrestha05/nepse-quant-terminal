---
title: 2026-11-20 - NEPSE Sector Lead-Lag
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
---

# NEPSE Sector Lead-Lag (2026-11-20)

- **Strategy ID:** `nepse_lead_lag`
- **Signals:** `lead_lag`
- **Description:** Intra-sector bellwether-to-laggard catch-up across liquid NEPSE sectors.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 27 | NPR 1,000,000 | NPR 1,774,958 | +77.50% | +8.69% | +8.69% | 0.61 | -31.74% | 253 | 45.8% | 72.27% | -12.22% | -0.99 |
| `lump_1l` (1L Lump Sum) | 25 | NPR 100,000 | NPR 209,578 | +109.58% | +11.34% | +11.34% | 0.71 | -40.23% | 217 | 46.1% | 96.96% | -5.84% | -0.39 |
| `sip_5k` (5K + 5K/BS Month) | 26 | NPR 415,000 | NPR 457,815 | +58.81% | +6.95% | +2.86% | 0.48 | -40.27% | 213 | 43.2% | 28.46% | -10.17% | -0.82 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +17.88% | 1.05 | -30.81% | 182 | -12.22% | -0.99 | -31.74% | 71 |
| `lump_1l` | +18.67% | 1.01 | -40.23% | 156 | -5.84% | -0.39 | -27.54% | 61 |
| `sip_5k` | +14.26% | 0.81 | -40.27% | 144 | -10.17% | -0.82 | -29.91% | 69 |

Related: [[2026-11-20 - Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
