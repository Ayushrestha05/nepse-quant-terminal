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

Add: implement `generate_*_at_date`, register in `SIGNAL_MAP`. Used by [[Tab Signals]], [[Validation Suite]], [[Strategy Registry]].
