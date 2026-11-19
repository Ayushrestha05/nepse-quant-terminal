---
title: Strategy Registry
tags: [component, strategies]
---

# Strategy Registry

`backend/trading/strategy_registry.py` + JSON under `data/strategy_registry/`.

Local: build in [[Tab Strategies]] (`N NEW`, toggle signals, `SAVE`, `→ ACTIVE ACCT`). Connected: nepsequant.com Lab/Screener strategies + [[Website Connect]] auto-trader (`apps/tui/io/strategy_autotrader.py`, ≤8 orders/min).

Config knobs: `signal_types`, `holding_days`, `max_positions`, stops, `use_regime_filter`, sector limits.

Related: [[Signal Engine]], [[Paper Trading]].
