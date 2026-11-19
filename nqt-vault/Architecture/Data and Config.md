---
title: Data and Config
tags: [architecture, data]
---

# Data and Config

| Path | Purpose |
|---|---|
| `data/` (mostly gitignored) | Runtime DB, caches, accounts |
| `data/strategy_registry/` | Committed builtin strategy JSON | → [[Strategy Registry]] |
| `configs/` | long/short term + MCP configs |
| `setup_data.py` | Download / scrape market DB (~13 MB snapshot) | → [[Market Data Ingestion]] |
| `~/.config/nepse-quant-terminal/` | Credentials + AI keys (local only) | → [[Connect nepsequant.com]], [[AI Setup]] |

Local paper accounts: `data/runtime/accounts/account_N/`.

Related: [[Architecture Overview]], [[Quick Start]].
