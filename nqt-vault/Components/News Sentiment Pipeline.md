---
title: News Sentiment Pipeline
tags: [component, nlp, sentiment, research]
---

# News Sentiment Pipeline

Scrapes MeroLagani / ShareSansar, scores Nepali+EN headlines, stores `sentiment_scores`, emits `NLP_SENTIMENT`.

Handoff doc (for AI engineer): `docs/research/NEWS_SENTIMENT_PIPELINE.md`.

- Ingest: `backend/quant_pro/data_scrapers/sentiment_ingestion.py`
- **Cache:** skip source if today's `sentiment_scores` exist; `--force` to refresh
- Signal: `backend/quant_pro/nepali_sentiment.py` (no look-ahead: `date < trade_date`)
- IC check: `python3 -m scripts.reporting.sentiment_ic`
- Optional fetch: `NQT_PROXIES`, `FIRECRAWL_API_KEY`
- Local LLM scoring: `--model llm` via [[AI Analyst]] / Ollama (`qwen3:4b`)

Related: [[Signal Engine]], [[AI Analyst]], [[Nepse Agents Graph]], [[Market Data Ingestion]], [[Change Log]].
