---
title: NEPSE IPO Listing Momentum (2026-11-20 13:29)
tags: [backtest, report, strategy]
status: active
date: 2026-11-20
run_stamp: 2026-11-20_1329
---

# NEPSE IPO Listing Momentum (2026-11-20 13:29)

- **Strategy ID:** `nepse_ipo_momentum`
- **Signals:** `ipo_momentum`
- **Description:** Post-IPO listing discovery momentum using verified ShareSansar IPO-only listing dates (excludes FPOs, mutual funds, rights, and mergers; falls back to post-2017 proxy if table empty).
- **Window:** `2020-01-01` → `2026-11-19` (In-Sample: `2020-01-01..2024-12-31`, Out-of-Sample: `2025-01-01..2026-11-19`)
- **Trade DB:** `data/backtests.db`

## Scenario Summary

| Scenario | Run ID | Contributed | Final NAV | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Win Rate | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | 48 | NPR 1,000,000 | NPR 254,904,417 | +25390.44% | +123.55% | +123.55% | 3.25 | -21.88% | 153 | 49.0% | 833.40% | +361.69% | 4.36 |
| `lump_1l` (1L Lump Sum) | 46 | NPR 100,000 | NPR 25,194,448 | +25094.45% | +123.17% | +123.17% | 3.19 | -22.02% | 153 | 48.4% | 966.01% | +358.48% | 4.34 |
| `sip_5k` (5K + 5K/BS Month) | 47 | NPR 415,000 | NPR 32,432,982 | +33893.41% | +133.09% | +144.87% | 3.22 | -22.01% | 153 | 48.4% | 289.33% | +358.87% | 4.35 |

## In-Sample (2020–2024) vs Out-of-Sample (2025–2026)

| Scenario | IS CAGR | IS Sharpe | IS Max DD | IS Trades | OOS CAGR | OOS Sharpe | OOS Max DD | OOS Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` | +70.24% | 2.76 | -20.14% | 107 | +361.69% | 4.36 | -21.88% | 46 |
| `lump_1l` | +70.29% | 2.66 | -20.41% | 107 | +358.48% | 4.34 | -22.02% | 46 |
| `sip_5k` | +80.74% | 2.69 | -20.37% | 107 | +358.87% | 4.35 | -22.01% | 46 |

Related: [[2026-11-20_1329/Strategy Comparison|Strategy Comparison]], [[Backtest Reports]], [[Strategy Catalog]], [[Backtesting Process]].
