---
title: Backtest Reports
tags: [moc, validation, backtest, reports]
status: active
---

# Backtest Reports

Dated paper-backtest run logs grouped by run timestamp (`YYYY-MM-DD_HHMM/`) so reports and charts stay tidy.

- **Folder layout:** `nqt-vault/Backtest Reports/YYYY-MM-DD_HHMM/` (`Strategy Comparison.md`, `<Strategy>.md`, `charts/nav_<scenario>.png`)
- **Standard scenarios:** Every backtest runs all 3 `CAPITAL_SCENARIOS` (`lump_10l`, `lump_1l`, `sip_5k`).
- **Trade store (gitignored):** `data/backtests.db` (`runs`, `trades`, `daily_nav`, `contributions`)
- **Latest comparison report:** [[2026-11-20_1329/Strategy Comparison|2026-11-20 13:29 — Strategy Comparison]]
- **Methodology & reproduction:** [[Baseline Backtest]] · [[Backtesting Process]] · [[Strategy Catalog]] · [[External Market Data Sources]] · [[Validation Suite]]

## Suite Runs (Newest First)

- [[2026-11-20_1329/Strategy Comparison|2026-11-20 1329 — Strategy Comparison]] (`2026-11-20_1329/`)
- [[2026-11-20_1108/Strategy Comparison|2026-11-20 1108 — Strategy Comparison]] (`2026-11-20_1108/`)

## Latest Run Tracker (`2026-11-20 13:29`)

| Run | Report | Strategy | Scenario | Window | Status | TWR Total | TWR CAGR | XIRR | Sharpe | Max DD | Trades |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-11-20 13:29 | [[2026-11-20_1329/C5 Baseline (NAV Sizing)|C5 Baseline (NAV Sizing)]] | `default_c5` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +180.35% | +16.14% | +16.14% | 0.95 | -54.62% | 196 |
| 2026-11-20 13:29 | [[2026-11-20_1329/C5 Baseline (NAV Sizing)|C5 Baseline (NAV Sizing)]] | `default_c5` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +75.15% | +8.48% | +8.48% | 0.54 | -54.54% | 171 |
| 2026-11-20 13:29 | [[2026-11-20_1329/C5 Baseline (NAV Sizing)|C5 Baseline (NAV Sizing)]] | `default_c5` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +42.46% | +5.27% | +5.86% | 0.38 | -53.58% | 165 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Book-Closure Run-Up|NEPSE Book-Closure Run-Up]] | `nepse_book_closure_runup` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +26.29% | +3.45% | +3.45% | 0.61 | -10.23% | 84 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Book-Closure Run-Up|NEPSE Book-Closure Run-Up]] | `nepse_book_closure_runup` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +29.60% | +3.84% | +3.84% | 0.58 | -13.13% | 83 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Book-Closure Run-Up|NEPSE Book-Closure Run-Up]] | `nepse_book_closure_runup` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +28.95% | +3.76% | +2.77% | 0.60 | -10.36% | 82 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Ex-Date Gap Rebound|NEPSE Ex-Date Gap Rebound]] | `nepse_ex_date_gap` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | -9.29% | -1.41% | -1.41% | -0.25 | -27.62% | 47 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Ex-Date Gap Rebound|NEPSE Ex-Date Gap Rebound]] | `nepse_ex_date_gap` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | -15.01% | -2.33% | -2.33% | -0.27 | -38.40% | 44 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Ex-Date Gap Rebound|NEPSE Ex-Date Gap Rebound]] | `nepse_ex_date_gap` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | -17.00% | -2.67% | -1.11% | -0.43 | -35.18% | 44 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Upper-Circuit Continuation|NEPSE Upper-Circuit Continuation]] | `nepse_circuit_continuation` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | -43.15% | -7.87% | -7.87% | -0.28 | -65.40% | 395 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Upper-Circuit Continuation|NEPSE Upper-Circuit Continuation]] | `nepse_circuit_continuation` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | -79.34% | -20.46% | -20.46% | -0.71 | -86.04% | 326 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Upper-Circuit Continuation|NEPSE Upper-Circuit Continuation]] | `nepse_circuit_continuation` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | -60.80% | -12.71% | -19.93% | -0.45 | -67.79% | 322 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE IPO Listing Momentum|NEPSE IPO Listing Momentum]] | `nepse_ipo_momentum` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +25390.44% | +123.55% | +123.55% | 3.25 | -21.88% | 153 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE IPO Listing Momentum|NEPSE IPO Listing Momentum]] | `nepse_ipo_momentum` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +25094.45% | +123.17% | +123.17% | 3.19 | -22.02% | 153 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE IPO Listing Momentum|NEPSE IPO Listing Momentum]] | `nepse_ipo_momentum` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +33893.41% | +133.09% | +144.87% | 3.22 | -22.01% | 153 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Sector Rotation|NEPSE Sector Rotation]] | `nepse_sector_rotation` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +52.09% | +6.28% | +6.28% | 0.40 | -43.48% | 254 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Sector Rotation|NEPSE Sector Rotation]] | `nepse_sector_rotation` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +100.74% | +10.65% | +10.65% | 0.56 | -39.95% | 232 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Sector Rotation|NEPSE Sector Rotation]] | `nepse_sector_rotation` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +92.27% | +9.96% | -1.95% | 0.52 | -41.74% | 222 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Post-Earnings Drift|NEPSE Post-Earnings Drift]] | `nepse_earnings_drift` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | -20.16% | -3.22% | -3.22% | -0.14 | -53.31% | 136 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Post-Earnings Drift|NEPSE Post-Earnings Drift]] | `nepse_earnings_drift` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | -34.08% | -5.87% | -5.87% | -0.26 | -60.27% | 104 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Post-Earnings Drift|NEPSE Post-Earnings Drift]] | `nepse_earnings_drift` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | -27.88% | -4.63% | -6.28% | -0.14 | -58.63% | 115 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Calendar & Festival Effects|NEPSE Calendar & Festival Effects]] | `nepse_calendar_festival` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +50.68% | +6.13% | +6.13% | 0.60 | -20.17% | 72 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Calendar & Festival Effects|NEPSE Calendar & Festival Effects]] | `nepse_calendar_festival` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +36.02% | +4.57% | +4.57% | 0.43 | -24.84% | 65 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Calendar & Festival Effects|NEPSE Calendar & Festival Effects]] | `nepse_calendar_festival` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +27.99% | +3.65% | +1.39% | 0.36 | -24.56% | 64 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE NRB Monetary Policy|NEPSE NRB Monetary Policy]] | `nepse_nrb_policy` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | -32.36% | -5.52% | -5.52% | -0.85 | -32.36% | 34 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE NRB Monetary Policy|NEPSE NRB Monetary Policy]] | `nepse_nrb_policy` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | -35.40% | -6.15% | -6.15% | -0.79 | -35.40% | 23 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE NRB Monetary Policy|NEPSE NRB Monetary Policy]] | `nepse_nrb_policy` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | -34.47% | -5.95% | -5.53% | -0.89 | -34.89% | 26 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Sector Lead-Lag|NEPSE Sector Lead-Lag]] | `nepse_lead_lag` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +77.50% | +8.69% | +8.69% | 0.61 | -31.74% | 253 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Sector Lead-Lag|NEPSE Sector Lead-Lag]] | `nepse_lead_lag` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +109.58% | +11.34% | +11.34% | 0.71 | -40.23% | 217 |
| 2026-11-20 13:29 | [[2026-11-20_1329/NEPSE Sector Lead-Lag|NEPSE Sector Lead-Lag]] | `nepse_lead_lag` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +58.81% | +6.95% | +2.86% | 0.48 | -40.27% | 213 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Event-Driven|Combo - Event-Driven]] | `combo_event_driven` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | -23.94% | -3.89% | -3.89% | -0.18 | -59.67% | 223 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Event-Driven|Combo - Event-Driven]] | `combo_event_driven` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | -33.51% | -5.75% | -5.75% | -0.23 | -66.72% | 194 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Event-Driven|Combo - Event-Driven]] | `combo_event_driven` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | -28.58% | -4.77% | -8.23% | -0.22 | -63.40% | 197 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Trend & Breakout|Combo - Trend & Breakout]] | `combo_trend` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +1388.48% | +48.00% | +48.00% | 1.47 | -43.55% | 406 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Trend & Breakout|Combo - Trend & Breakout]] | `combo_trend` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +1143.74% | +44.19% | +44.19% | 1.36 | -48.23% | 393 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Trend & Breakout|Combo - Trend & Breakout]] | `combo_trend` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +1204.16% | +45.19% | +36.72% | 1.36 | -48.15% | 371 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Top 3 Solo (IS Sharpe)|Combo - Top 3 Solo (IS Sharpe)]] | `combo_top3_sharpe` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +1987.78% | +55.45% | +55.45% | 1.76 | -36.43% | 330 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Top 3 Solo (IS Sharpe)|Combo - Top 3 Solo (IS Sharpe)]] | `combo_top3_sharpe` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +1837.77% | +53.78% | +53.78% | 1.71 | -39.83% | 317 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Top 3 Solo (IS Sharpe)|Combo - Top 3 Solo (IS Sharpe)]] | `combo_top3_sharpe` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +1714.42% | +52.32% | +49.72% | 1.61 | -44.41% | 291 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Top 5 Solo (IS Sharpe)|Combo - Top 5 Solo (IS Sharpe)]] | `combo_top5_sharpe` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +1885.72% | +54.33% | +54.33% | 1.75 | -36.95% | 341 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Top 5 Solo (IS Sharpe)|Combo - Top 5 Solo (IS Sharpe)]] | `combo_top5_sharpe` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +1857.36% | +54.00% | +54.00% | 1.73 | -40.06% | 333 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - Top 5 Solo (IS Sharpe)|Combo - Top 5 Solo (IS Sharpe)]] | `combo_top5_sharpe` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +1819.72% | +53.57% | +51.01% | 1.63 | -41.83% | 303 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - C5 Plus Best New (ipo_momentum)|Combo - C5 Plus Best New (ipo_momentum)]] | `combo_c5_plus_best` | `lump_10l` | `2020-01-01` → `2026-11-19` | complete | +3799.64% | +70.21% | +70.21% | 2.38 | -39.70% | 232 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - C5 Plus Best New (ipo_momentum)|Combo - C5 Plus Best New (ipo_momentum)]] | `combo_c5_plus_best` | `lump_1l` | `2020-01-01` → `2026-11-19` | complete | +2217.08% | +57.82% | +57.82% | 2.02 | -40.38% | 232 |
| 2026-11-20 13:29 | [[2026-11-20_1329/Combo - C5 Plus Best New (ipo_momentum)|Combo - C5 Plus Best New (ipo_momentum)]] | `combo_c5_plus_best` | `sip_5k` | `2020-01-01` → `2026-11-19` | complete | +1600.44% | +50.89% | +57.21% | 1.82 | -38.61% | 211 |
| 2026-11-20 (legacy) | [[2026-11-20 - C5 Baseline]] | `default_c5` | `lump_10l` *(fixed-cap sizing)* | `2020-01-01` → `2026-11-19` | complete | +121.09% | +12.21% | — | 1.07 | -26.14% | 209 |
| 2026-11-20 (legacy) | [[2026-11-20 - C5 Baseline (Partial)]] | `default_c5` | `lump_10l` *(fixed-cap)* | `2020-01-01` → `2025-02-10` | partial | +109.45% | +15.56% | — | — | -22.07%* | 160 |

\*Checkpoint floor from 50-day log intervals; true daily drawdown is at least this magnitude.

Related: [[00 - Index]], [[Baseline Backtest]], [[Backtesting Process]], [[Strategy Catalog]], [[Signal Engine]], [[Strategy Registry]], [[Change Log]].
