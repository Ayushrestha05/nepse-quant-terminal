---
title: Signal Engine
tags: [component, signals, backtest]
---

# Signal Engine

`backend/backtesting/simple_backtest.py`. Scores 0–1 per symbol/date; regime-weighted (60-day NEPSE return → bull/neutral/bear). Default fire every 5 trading days.

| Signal | Idea |
|---|---|
| `volume` | Breakout vs 20d avg + price confirm |
| `quality` | ROE, D/E, earnings stability |
| `low_vol` | Low 60d vol + positive momentum |
| `mean_reversion` | RSI oversold / below 52w high |
| `xsec_momentum` | 6m−1m cross-sectional |
| `quarterly_fundamental` | EPS/revenue growth |
| `satellite_hydro` | Rainfall / hydro |
| `book_closure_runup` | Pre-bookclose dividend/bonus run-up (3–15d notice window, exits T-1) |
| `ex_date_gap` | Post-ex-date bonus/rights adjustment rebound |
| `circuit_continuation` | Upper-circuit (+8.5%+) high-volume breakout continuation (exempt from CB reversal filter) |
| `ipo_momentum` | Post-IPO listing discovery momentum (non-merger, exempt from CB reversal filter) |
| `sector_rotation` | Equal-weighted causal synthetic sector index rotation |
| `earnings_drift` | Post-earnings announcement drift (`quarterly_earnings.announcement_date`) |
| `calendar_festival` | Ashad fiscal year-end rebound + Dashain/Tihar flows (`nepdate-core` + `nepdate-patro`) |
| `nrb_policy` | Post-NRB annual Monetary Policy BFI follow-through |
| `lead_lag` | Intra-sector bellwether-to-laggard catch-up |

NEPSE-specific generators live in `backend/backtesting/nepse_event_signals.py` with calendar utilities in `backend/quant_pro/nepal_calendar.py`.

Add: implement `generate_*_at_date` using `_history(..., symbol_cache=symbol_cache)` (never scan `prices_df` when `symbol_cache` is present), register in `SignalType` (`backend/quant_pro/alpha_practical.py`), and wire into `run_backtest`. Used by [[Tab Signals]], [[Backtesting Process]], [[Validation Suite]], [[Strategy Registry]], [[Strategy Catalog]].
