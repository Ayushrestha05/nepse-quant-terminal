---
title: Strategy Registry
tags: [component, strategies]
---

# Strategy Registry

`backend/trading/strategy_registry.py` + JSON under `data/strategy_registry/`.

Built-in strategies under `data/strategy_registry/builtin/`:
- Baselines: `default_c5`, `temp_forward_winner`
- 9 NEPSE solo strategies: `nepse_book_closure_runup`, `nepse_ex_date_gap`, `nepse_circuit_continuation`, `nepse_ipo_momentum`, `nepse_sector_rotation`, `nepse_earnings_drift`, `nepse_calendar_festival`, `nepse_nrb_policy`, `nepse_lead_lag`
- 5 combinations: `combo_event_driven`, `combo_trend`, `combo_top3_sharpe`, `combo_top5_sharpe`, `combo_c5_plus_best` (data-selected combos chosen strictly from 2020–2024 in-sample Sharpe)

See [[Strategy Catalog]] for signal definitions and data sources.

Local: build in [[Tab Strategies]] (`N NEW`, toggle signals, `SAVE`, `→ ACTIVE ACCT`). Connected: nepsequant.com Lab/Screener strategies + [[Website Connect]] auto-trader (`apps/tui/io/strategy_autotrader.py`, ≤8 orders/min).

Config knobs: `signal_types`, `holding_days`, `max_positions`, stops, `use_regime_filter`, sector limits.

Related: [[Signal Engine]], [[Strategy Catalog]], [[Paper Trading]], [[Backtest Reports]].
