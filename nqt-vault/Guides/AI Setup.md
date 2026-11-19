---
title: AI Setup
tags: [guide, ai]
---

# AI Setup

```bash
./nqt-connect ai setup     # ollama | openai | anthropic
./nqt-connect ai status
./nqt-connect ai off
```

Keys in `~/.config/nepse-quant-terminal/ai.json`. In-tab: `/agent …`, `/model …`.

Default local model: **`qwen3:4b`** (llmfit fit for RTX 4050 6GB). User-local binary: `~/.local/bin/ollama`. Prefer system `ollama-cuda` via pacman when you want a service.

```bash
export PATH="$HOME/.local/bin:$PATH"
ollama serve
ollama pull qwen3:4b
```

Sentiment LLM scoring: `python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --model llm` — see [[News Sentiment Pipeline]].

See [[AI Analyst]], [[Tab Agents]].
