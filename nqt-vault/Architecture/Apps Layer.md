---
title: Apps Layer
tags: [architecture, apps]
---

# Apps Layer

Top-level runnable surfaces under `apps/`.

| Package | Role | Links |
|---|---|---|
| `apps/tui/` | Textual terminal UI | [[TUI Dashboard]], tabs |
| `apps/cli/connect.py` | `./nqt-connect` — keys, status, paper/real portfolio | [[Website Connect]], [[Connect nepsequant.com]] |
| `apps/mcp/` | MCP server surface | [[Developer Workflow]] |

TUI splits into `io/` (fetchers, website_*, orders), `render/`, `screens/`, `state/mixins/`, `widgets/`.

Upstream: [[Architecture Overview]]. Downstream: [[Backend Layer]].
