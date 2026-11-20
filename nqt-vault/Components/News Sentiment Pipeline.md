---
title: News Sentiment Pipeline
tags: [component, nlp, sentiment, research]
---

# News Sentiment Pipeline

Scrapes MeroLagani / ShareSansar, scores Nepali+EN headlines, stores `sentiment_scores`, emits `NLP_SENTIMENT`.

Handoff doc (for AI engineer): `docs/research/NEWS_SENTIMENT_PIPELINE.md`.

- Ingest: `backend/quant_pro/data_scrapers/sentiment_ingestion.py`
- **Historical backfill:** `--backfill --start-id 55000 --model xlm-roberta --batch-size 64 --rps 1.0 --proxy-only` walks Merolagani `NewsDetail.aspx?newsID=<id>` (resumes from max stored `newsID` in `news`, UTF-8 decoded, stores every article in `news` and batch-scores all articles with `cardiffnlp/twitter-xlm-roberta-base-sentiment` into `sentiment_scores` by recomputing touched dates).
- **Cache:** skip source if today's `sentiment_scores` exist; `--force` to refresh
- Signal: `backend/quant_pro/nepali_sentiment.py` (no look-ahead: `date < trade_date`); registered as `nepse_nlp_sentiment` in `data/strategy_registry/builtin/`
- IC check: `python3 -m scripts.reporting.sentiment_ic`
- Optional fetch: shared HTTPS `proxy_pool.py` (`NQT_PROXIES`, `NQT_PROXY_ONLY=1`), `FIRECRAWL_API_KEY`
- Local LLM scoring: `--model llm` via [[AI Analyst]] / Ollama (`qwen3:4b`) — daily runs only (never backfill)

Related: [[Signal Engine]], [[AI Analyst]], [[Nepse Agents Graph]], [[Market Data Ingestion]], [[Change Log]].
