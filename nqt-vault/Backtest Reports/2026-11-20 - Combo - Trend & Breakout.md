---
title: 2026-11-20 - Combo - Trend & Breakout
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
---

# Combo: Trend & Breakout (2026-11-20)

- **Strategy ID:** `combo_trend`
- **Signals:** `circuit_continuation, ipo_momentum, sector_rotation`
- **Description:** Trend NEPSE combo: Upper-Circuit Continuation + IPO Momentum + Sector Rotation.
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 32 | NPR 1,000,000 | NPR 14,884,752 | +1388.48% | +48.00% | +48.00% | 1.47 | -43.55% | 406 | 35.5% | 375.79% | +44.73% | 1.36 |
| `lump_1l` (1L Lump Sum) | 30 | NPR 100,000 | NPR 1,243,739 | +1143.74% | +44.19% | +44.19% | 1.36 | -48.23% | 393 | 34.4% | 437.97% | +36.06% | 1.17 |
| `sip_5k` (5K + 5K/BS Month) | 33 | NPR 415,000 | NPR 1,466,666 | +1204.16% | +45.19% | +36.72% | 1.36 | -48.15% | 371 | 31.5% | 104.30% | +36.10% | 1.17 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +48.56% | 1.49 | -40.54% | 297 | +44.73% | 1.36 | -43.55% | 109 |
| `lump_1l` | +46.70% | 1.42 | -40.60% | 284 | +36.06% | 1.17 | -44.04% | 109 |
| `sip_5k` | +48.09% | 1.42 | -40.50% | 262 | +36.10% | 1.17 | -44.03% | 109 |

Related: [[2026-11-20 - Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
