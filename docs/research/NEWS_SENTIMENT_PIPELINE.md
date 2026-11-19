# News Sentiment Pipeline — AI Engineer Handoff

Date: 2026-11-20  
Audience: AI engineer continuing Nepali financial NLP for NEPSE Quant Terminal.

## What already exists

| Piece | Path | Role |
| --- | --- | --- |
| Scraper + scorer | `backend/quant_pro/data_scrapers/sentiment_ingestion.py` | MeroLagani + ShareSansar → scores → SQLite |
| Signal | `backend/quant_pro/nepali_sentiment.py` | `NLP_SENTIMENT` AlphaSignal for backtests |
| Table | `sentiment_scores` in `backend/quant_pro/database.py` | `(date, symbol, source, model)` PK |
| Local LLM | `backend/agents/llm_ollama.py` | Ollama chat + tools; default `qwen3:4b` |
| Agent graph | `backend/nepse_agents/orchestrator.py` | Paper decision graph + bounded validate loop |
| IC check | `scripts/reporting/sentiment_ic.py` | Rank IC vs next-day returns |

```text
sites → _fetch_url (urllib → NQT_PROXIES → FIRECRAWL_API_KEY)
     → articles (title, date_str/published_at, source)
     → score (nepali-xlmr | fin-qwen | xlm-roberta | keyword | llm)
     → sentiment_scores
     → nepali_sentiment (date < trade_date) → NLP_SENTIMENT
     → sentiment_ic.py (keep or kill the weight)
```

## Schema (signal input)

`sentiment_scores`:

- `date` — **publication calendar day** (from headline timestamp). Signal query uses `date < trade_date` (no look-ahead).
- `symbol` — ticker or NULL for market-wide.
- `source` — `merolagani` / `sharesansar`.
- `model` — e.g. `nepali-xlmr`, `fin-qwen`, `keyword`, `ollama-qwen3:4b`.
- `score` — `[-1, 1]`; `confidence`; `n_documents`; `scraped_at_utc`.

## Fetching

Env (all optional; off = unchanged behaviour):

- `NQT_PROXIES` — comma-separated proxy URLs, rotated on 403/429/timeout. Public GETs only.
- `FIRECRAWL_API_KEY` — Firecrawl cloud scrape fallback.
- `FIRECRAWL_API_URL` — default `https://api.firecrawl.dev/v1/scrape`.

Do **not** self-host Firecrawl until IC proves the signal is worth the RAM.

## Scoring modes

```bash
python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --model auto
python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --model nepali-xlmr
python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --model fin-qwen
python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --model llm
python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --model keyword
```

`auto` order: `nepali-xlmr` → `fin-qwen` → `xlm-roberta` → keyword.

| Model | HF id | Why |
| --- | --- | --- |
| **Use** nepali-xlmr | `AurevinP/xlm-roberta-base-nepali-sentiment-v1` | Large Nepali fine-tune (~125k), Devanagari + Romanized + code-mix |
| **Use** fin-qwen | `NOSIBLE/financial-sentiment-v1.2-base` | Multilingual *financial impact* sentiment (Qwen3-0.6B) |
| Keep | `cardiffnlp/twitter-xlm-roberta-base-sentiment` | Previous default; still in chain |
| **Skip** | `robinGiri2024/nepse-sentiment-analyzer` | Keras BiLSTM, ~3k samples, no published tokenizer/preprocess |
| LLM mode | Ollama `qwen3:4b` | JSON `{tickers, event_type, sentiment, score, confidence}` + name→ticker map from `market_quotes.security_name` |

## Fine-tune recipe (option C)

Goal: small Nepali financial classifier that beats keyword + general Nepali XLM-R on NEPSE headlines.

1. **Base:** `IRIIS-RESEARCH/RoBERTa_Nepali_125M` (or continue from AurevinP checkpoint if labels match).
2. **Seed data:** `sand3shog/NepaliSentiment` (NEPSE comments mixed with politics — filter hard).
3. **Bootstrap labels:** run `--model llm` over scraped headlines; keep only `confidence >= 0.7`; human-spot-check 200 rows.
4. **Split by date** (never random): train `< T`, val `[T, T+30d)`, test `>= T+30d`.
5. **Metrics:** macro-F1 on labels **and** out-of-sample Spearman IC via `python3 -m scripts.reporting.sentiment_ic`.
6. Ship only if mean IC is clearly > ~0.02 with stable sign across months.

## Evaluation protocol

```bash
python3 -m scripts.reporting.sentiment_ic --days 120
```

- **Mean daily Spearman IC** of cross-sectional sentiment vs next-day return.
- **Hit rate** of score sign vs return sign.
- If IC ≈ 0 → do not weight `NLP_SENTIMENT` in the live book.

Hard rules:

- Use only `date < trade_date`.
- Prefer per-symbol scores; market-wide is a tilt only.
- Entity linking (name → ticker) matters more than swapping classifiers.

## Hardware / local LLM (this machine)

- CPU: i5-13420H (12 threads), RAM ~15 GB.
- GPU: RTX 4050 Laptop **6 GB** VRAM (driver works; sandbox may hide it).
- Ollama: user-local at `~/.local/bin/ollama` (v0.40.16); model `qwen3:4b` (~2.5 GB).
- Suggested default in code: `SUGGESTED_MODEL = "qwen3:4b"` (tool-calling capable, fits 6 GB).
- Alt: `qwen2.5:7b` if quality matters more than speed.
- Permanent system install (optional): `sudo pacman -S ollama-cuda` on CachyOS, then `ollama serve` / systemd.

```bash
export PATH="$HOME/.local/bin:$PATH"
ollama serve   # if not already running
ollama list    # expect qwen3:4b
```

## Open questions for you

1. Same-day post-close trading vs next-open — confirm the `< trade_date` rule matches your fill assumption.
2. Extra sources (ShareHub, corporation filings) — only after IC > 0.
3. Fine-tune label taxonomy: 3-class vs 5-class; map to continuous `score`.
4. Whether `event_type` should graduate into `news_event_scores` (table already exists) once volume justifies it.

## Quick verify

```bash
pytest tests/unit/test_sentiment_llm_parse.py tests/unit/test_nepse_agents_public.py -q
python3 -m scripts.reporting.sentiment_ic --days 30
```
