---
title: Strategy Catalog
tags: [component, strategies, nepse, backtest]
status: active
---

# Strategy Catalog

Catalog of NEPSE-specific solo strategies and combinations registered under `data/strategy_registry/builtin/` and implemented in `backend/backtesting/nepse_event_signals.py` + `backend/backtesting/simple_backtest.py`.

## Solo NEPSE Strategies (9)

| Strategy ID | Signal Type | Core Idea | Primary Data Source |
| --- | --- | --- | --- |
| `nepse_book_closure_runup` | `book_closure_runup` | Pre-bookclose run-up on >=10% cash/bonus dividends (3–15d statutory notice window, exits T-1) | `corporate_actions`, `stock_prices` |
| `nepse_ex_date_gap` | `ex_date_gap` | Post-ex-date rebound after bonus (>=10%) or right-share price adjustments | `corporate_actions`, `stock_prices` |
| `nepse_circuit_continuation` | `circuit_continuation` | Upper-circuit (+8.5%+) close-near-high breakout continuation with >=1.5x volume (exempt from CB reversal filter) | `stock_prices` |
| `nepse_ipo_momentum` | `ipo_momentum` | Post-IPO discovery momentum (days 5–45 after first trading day > 2017, excludes merger mentions; exempt from CB reversal filter) | `stock_prices`, `corporate_actions` |
| `nepse_sector_rotation` | `sector_rotation` | Equal-weighted causal synthetic sector indices across `SECTOR_GROUPS`; buys top-2 leading sectors' strongest liquid stocks | `stock_prices`, `sectors.py` |
| `nepse_earnings_drift` | `earnings_drift` | Post-earnings announcement drift (PEAD): >=+15% YoY/QoQ net-profit/EPS growth within 12d of `announcement_date` + price/volume confirm | `quarterly_earnings`, `stock_prices` |
| `nepse_calendar_festival` | `calendar_festival` | Ashad fiscal year-end liquidity rebound + pre-Dashain / post-Tihar remittance liquidity flows (`nepdate-core` + `nepdate-patro`) | `nepal_calendar.py`, `stock_prices` |
| `nepse_nrb_policy` | `nrb_policy` | Post-NRB annual Monetary Policy follow-through in rate-sensitive BFI sectors | `nepal_calendar.py`, `stock_prices` |
| `nepse_lead_lag` | `lead_lag` | Intra-sector catch-up: buys liquid sector laggards after top-3 turnover bellwethers rally >=+4% over 5d | `stock_prices`, `sectors.py` |

## Combination Strategies (5)

| Strategy ID | Selection Basis | Signals |
| --- | --- | --- |
| `combo_event_driven` | Thematic (fixed) | `book_closure_runup`, `ex_date_gap`, `earnings_drift` |
| `combo_trend` | Thematic (fixed) | `circuit_continuation`, `ipo_momentum`, `sector_rotation` |
| `combo_top3_sharpe` | Top 3 solo by 2020–2024 in-sample Sharpe | Written by `run_strategy_suite.py` |
| `combo_top5_sharpe` | Top 5 solo by 2020–2024 in-sample Sharpe | Written by `run_strategy_suite.py` |
| `combo_c5_plus_best` | C5 + #1 solo by 2020–2024 in-sample Sharpe | Written by `run_strategy_suite.py` |

## Deferred (Tracked in root `TODO.md`)

- **Broker concentration / informed trading (`informed_trading`)**: blocked — `floorsheet_trades`, `broker_summary`, and `broker_signal_scores` are currently empty.
- **News sentiment (`nlp_sentiment`)**: blocked — `news` and `sentiment_scores` are currently empty.

Related: [[Strategy Registry]], [[Signal Engine]], [[Backtesting Process]], [[Backtest Reports]], [[Baseline Backtest]], [[00 - Index]].
