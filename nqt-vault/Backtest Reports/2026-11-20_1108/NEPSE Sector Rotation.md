---
title: NEPSE Sector Rotation (2026-11-20 11:08)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1108
---

# NEPSE Sector Rotation (2026-11-20 11:08)

- **Strategy ID:** `nepse_sector_rotation`
- **Signals:** `sector_rotation`
- **Description:** Sector rotation across NEPSE sectors using causal equal-weighted synthetic sector indices.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 12 | NPR 1,000,000 | NPR 1,520,862 | +52.09% | +6.28% | +6.28% | 0.40 | -43.48% | 254 | 33.5% | 81.93% | -16.09% | -0.92 |
| `lump_1l` (1L Lump Sum) | 11 | NPR 100,000 | NPR 200,737 | +100.74% | +10.65% | +10.65% | 0.56 | -39.95% | 232 | 34.1% | 106.90% | -13.14% | -0.60 |
| `sip_5k` (5K + 5K/BS Month) | 10 | NPR 415,000 | NPR 388,224 | +92.27% | +9.96% | -1.95% | 0.52 | -41.74% | 222 | 33.8% | 29.89% | -14.77% | -0.78 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +16.00% | 0.78 | -28.98% | 195 | -16.09% | -0.92 | -36.25% | 59 |
| `lump_1l` | +21.04% | 0.92 | -35.45% | 175 | -13.14% | -0.60 | -35.35% | 57 |
| `sip_5k` | +20.86% | 0.88 | -36.92% | 162 | -14.77% | -0.78 | -34.95% | 60 |

Related: [[2026-11-20_1108/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
