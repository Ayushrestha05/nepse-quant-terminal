---
title: Nepse Agents Graph
tags: [component, agents, paper]
---

# Nepse Agents Graph

`backend/nepse_agents/` — evidence-gated research → debate → risk → portfolio (paper only). See package README and `docs/assets/nepse-agent-architecture.png`.

After research, a bounded validate step (≤2 rounds) rechecks evidence against the plan (Dexter-style plan/check/stop). Audit trail: `validation_rounds` on the run record.

MCP setup runbook: `docs/runbooks/MCP_AGENT_SETUP.md`.

Related: [[AI Analyst]], [[News Sentiment Pipeline]], [[Apps Layer]] (`apps/mcp/`), [[Disclaimer]].
