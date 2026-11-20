---
title: C5 Baseline (NAV Sizing) (2026-11-20 13:29)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1329
---

# C5 Baseline (2026-11-20 13:29)

- **Strategy ID:** `default_c5`
- **Signals:** `volume, quality, low_vol, mean_reversion, quarterly_fundamental, xsec_momentum`
- **Description:** C5 Baseline — 6-signal factor model with regime filter. Vol+Quality+LowVol+MeanReversion+QF+XsecMomentum, 40 trading day holds.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 42 | NPR 1,000,000 | NPR 2,803,468 | +180.35% | +16.14% | +16.14% | 0.95 | -54.62% | 196 | 40.8% | 70.70% | +15.79% | 1.26 |
| `lump_1l` (1L Lump Sum) | 44 | NPR 100,000 | NPR 175,149 | +75.15% | +8.48% | +8.48% | 0.54 | -54.54% | 171 | 38.6% | 68.17% | +12.12% | 0.88 |
| `sip_5k` (5K + 5K/BS Month) | 45 | NPR 415,000 | NPR 507,799 | +42.46% | +5.27% | +5.86% | 0.38 | -53.58% | 165 | 40.0% | 19.25% | +15.11% | 1.22 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +16.19% | 0.90 | -54.62% | 151 | +15.79% | 1.26 | -14.56% | 45 |
| `lump_1l` | +7.19% | 0.46 | -54.54% | 130 | +12.12% | 0.88 | -20.69% | 41 |
| `sip_5k` | +1.70% | 0.19 | -53.58% | 120 | +15.11% | 1.22 | -14.64% | 45 |

Related: [[2026-11-20_1329/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
