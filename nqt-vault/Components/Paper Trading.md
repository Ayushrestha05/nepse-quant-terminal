---
title: Paper Trading
tags: [component, trading]
---

# Paper Trading

- `backend/trading/paper_execution.py` — account-scoped paper orders/fills
- `backend/trading/tui_trading_engine.py` — local auto-trade loop (holds, stops, regime)
- `backend/trading/paper_trade_tracker.py` — tracking
- Website path: orders via [[Website Connect]] simulator (NEPSE rules, fees, T+2)

Connected book refreshes ~30s. Override: `NQT_SHARED_BOOK=0`.

Related: [[Strategy Registry]], [[Tab Orders]], [[Tab Portfolio]], [[Disclaimer]].
