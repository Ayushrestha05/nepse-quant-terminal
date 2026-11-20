"""
Sentiment data ingestion from MeroLagani and ShareSansar news.

Scrapes NEPSE-related news headlines, scores them using NLP models
(XLM-RoBERTa / fin-qwen / Ollama LLM or keyword fallback), and stores
aggregated daily sentiment scores in the sentiment_scores table.

Usage:
    python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion
    python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --pages 5 --model keyword
    python3 -m backend.quant_pro.data_scrapers.sentiment_ingestion --model llm

Sources:
    - MeroLagani news: https://merolagani.com/NewsList.aspx
    - ShareSansar news: https://www.sharesansar.com/category/latest

Models (auto priority):
    1. AurevinP/xlm-roberta-base-nepali-sentiment-v1 (nepali-xlmr)
    2. NOSIBLE/financial-sentiment-v1.2-base (fin-qwen)
    3. cardiffnlp/twitter-xlm-roberta-base-sentiment (xlm-roberta)
    4. Keyword fallback

Optional: --model llm uses local Ollama for tickers + event_type + sentiment.
Fetcher: urllib → NQT_PROXIES → FIRECRAWL_API_KEY (all optional).
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import ProxyHandler, Request, build_opener, urlopen
from urllib.error import URLError, HTTPError
from backend.quant_pro.paths import get_data_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = get_data_dir(__file__) / "nepse_market_data.db"

# Rate limit: 1 request per second
REQUEST_DELAY = 1.0

# --- Keyword-based sentiment scorer (fallback) ---

POSITIVE_KEYWORDS_NP = [
    "बढ्यो", "बढेको", "वृद्धि", "लाभांश", "बोनस", "मुनाफा", "सकारात्मक",
    "राम्रो", "उच्च", "बढ्दो", "शेयर बढ्यो", "नाफा", "सुधार", "उत्साहजनक",
    "आईपीओ", "लगानी", "प्रगति", "विकास", "सफल", "रेकर्ड", "उत्कृष्ट",
]
POSITIVE_KEYWORDS_EN = [
    "profit", "increase", "bullish", "growth", "dividend", "bonus",
    "ipo", "record", "high", "surge", "rally", "gain", "rise",
    "strong", "positive", "improve", "uptrend", "breakout",
]

NEGATIVE_KEYWORDS_NP = [
    "घट्यो", "घटेको", "गिरावट", "नोक्सान", "ऋणात्मक", "खराब", "न्यून",
    "घट्दो", "शेयर घट्यो", "क्षति", "समस्या", "चिन्ता", "जोखिम",
    "मन्दी", "दुर्घटना", "बन्द", "स्थगित", "कारबाही", "जरिवाना",
]
NEGATIVE_KEYWORDS_EN = [
    "loss", "decrease", "bearish", "decline", "crash", "fall",
    "drop", "negative", "risk", "concern", "weak", "downtrend",
    "circuit breaker", "suspend", "penalty", "fine", "fraud",
]

ALL_POSITIVE = set(POSITIVE_KEYWORDS_NP + POSITIVE_KEYWORDS_EN)
ALL_NEGATIVE = set(NEGATIVE_KEYWORDS_NP + NEGATIVE_KEYWORDS_EN)

# Common NEPSE stock symbols for entity extraction
# (loaded from DB at runtime if available)
_CACHED_SYMBOLS: Optional[set] = None


def _load_symbols_from_db(db_path: str) -> set:
    """Load NEPSE symbols from the database."""
    global _CACHED_SYMBOLS
    if _CACHED_SYMBOLS is not None:
        return _CACHED_SYMBOLS
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM stock_prices WHERE symbol NOT LIKE 'SECTOR::%' AND symbol != 'NEPSE'")
        symbols = {row[0] for row in cursor.fetchall()}
        conn.close()
        _CACHED_SYMBOLS = symbols
        return symbols
    except Exception:
        _CACHED_SYMBOLS = set()
        return set()


_CACHED_NAME_MAP: Optional[Dict[str, str]] = None


def _load_name_to_symbol(db_path: str) -> Dict[str, str]:
    """Map lowercased company/security names → ticker from market_quotes."""
    global _CACHED_NAME_MAP
    if _CACHED_NAME_MAP is not None:
        return _CACHED_NAME_MAP
    mapping: Dict[str, str] = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT symbol, security_name FROM market_quotes
            WHERE security_name IS NOT NULL AND TRIM(security_name) != ''
            """
        )
        for symbol, name in cursor.fetchall():
            key = str(name or "").strip().lower()
            if key and symbol:
                mapping[key] = str(symbol).upper()
        conn.close()
    except Exception as e:
        logger.debug("name→symbol map unavailable: %s", e)
    _CACHED_NAME_MAP = mapping
    return mapping


def _extract_symbols_from_text(text: str, known_symbols: set) -> List[str]:
    """Extract stock symbols mentioned in text."""
    found = []
    text_upper = text.upper()
    for sym in known_symbols:
        # Match as a word boundary (not substring of another word)
        if re.search(rf'\b{re.escape(sym)}\b', text_upper):
            found.append(sym)
    return found


def _proxy_list() -> List[str]:
    from backend.quant_pro.data_scrapers.proxy_pool import parse_proxy_env
    return parse_proxy_env()


def _default_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,ne;q=0.3",
    }


def _fetch_via_urllib(url: str, timeout: int, proxy: Optional[str] = None) -> str:
    req = Request(url, headers=_default_headers())
    if proxy:
        opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _fetch_via_firecrawl(url: str, timeout: int = 60) -> str:
    """Optional Firecrawl cloud scrape when FIRECRAWL_API_KEY is set."""
    api_key = (os.environ.get("FIRECRAWL_API_KEY") or "").strip()
    if not api_key:
        return ""
    endpoint = (os.environ.get("FIRECRAWL_API_URL") or "https://api.firecrawl.dev/v1/scrape").strip()
    body = json.dumps({"url": url, "formats": ["html"], "onlyMainContent": False}).encode("utf-8")
    req = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        html = data.get("html") or data.get("rawHtml") or ""
        if html:
            return str(html)
        markdown = data.get("markdown") or ""
        if markdown:
            return f"<html><body><pre>{markdown}</pre></body></html>"
    return ""


def _is_block_error(exc: BaseException) -> bool:
    if isinstance(exc, HTTPError) and exc.code in (403, 429, 503):
        return True
    if isinstance(exc, (TimeoutError,)):
        return True
    if isinstance(exc, URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError,)):
            return True
        msg = str(reason or exc).lower()
        return "timed out" in msg or "timeout" in msg
    return False


# --- Scrapers ---

def _fetch_url(url: str, timeout: int = 15, *, proxy_only: Optional[bool] = None) -> str:
    """Fetch URL: shared HTTPS proxy pool in proxy-only mode; else direct → proxies → Firecrawl."""
    from backend.quant_pro.data_scrapers.proxy_pool import (
        ProxyPoolError,
        get_proxy_pool,
        is_proxy_only,
    )

    use_proxy_only = is_proxy_only() if proxy_only is None else bool(proxy_only)
    if use_proxy_only:
        pool = get_proxy_pool(proxy_only=True)
        resp = pool.get(url, headers=_default_headers(), timeout=timeout)
        return resp.content.decode("utf-8", errors="replace") if resp.status_code == 200 else ""

    try:
        return _fetch_via_urllib(url, timeout=timeout)
    except (URLError, HTTPError, TimeoutError) as e:
        if not _is_block_error(e):
            logger.warning("Failed to fetch %s: %s", url, e)
            return ""
        logger.info("Direct fetch blocked for %s (%s); trying proxies/Firecrawl", url, e)

    for proxy in _proxy_list():
        try:
            html = _fetch_via_urllib(url, timeout=timeout, proxy=proxy)
            if html:
                return html
        except (URLError, HTTPError, TimeoutError) as e:
            logger.debug("Proxy %s failed for %s: %s", proxy, url, e)
            continue

    if (os.environ.get("FIRECRAWL_API_KEY") or "").strip():
        try:
            html = _fetch_via_firecrawl(url)
            if html:
                return html
        except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as e:
            logger.warning("Firecrawl failed for %s: %s", url, e)

    logger.warning("Failed to fetch %s after urllib/proxy/Firecrawl", url)
    return ""


def scrape_merolagani_news(pages: int = 3) -> List[Dict]:
    """
    Scrape news headlines from MeroLagani.

    URL pattern: https://merolagani.com/NewsList.aspx?page=N
    Each headline has: title, date, URL with newsID

    Returns list of dicts with keys: title, url, date_str, source
    """
    articles = []
    base_url = "https://merolagani.com"

    for page in range(1, pages + 1):
        url = f"{base_url}/NewsList.aspx?page={page}"
        logger.info(f"Fetching MeroLagani page {page}/{pages}: {url}")
        html = _fetch_url(url)
        if not html:
            continue

        # Extract news articles using regex on the HTML
        # Pattern: <a href="/NewsDetail.aspx?newsID=XXXXX">HEADLINE</a>
        # Date pattern: "Feb 13, 2026 05:55 PM" or similar
        news_pattern = re.compile(
            r'<a[^>]*href="(/NewsDetail\.aspx\?newsID=\d+)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        date_pattern = re.compile(
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+(?:AM|PM))'
        )

        matches = news_pattern.findall(html)
        dates = date_pattern.findall(html)

        for i, (href, title_raw) in enumerate(matches):
            title = unescape(re.sub(r'<[^>]+>', '', title_raw)).strip()
            if not title or len(title) < 10:
                continue

            # Try to associate a date
            date_str = ""
            if i < len(dates):
                date_str = dates[i]

            articles.append({
                "title": title,
                "url": f"{base_url}{href}",
                "date_str": date_str,
                "source": "merolagani",
            })

        time.sleep(REQUEST_DELAY)

    logger.info(f"Scraped {len(articles)} articles from MeroLagani")
    return articles


def scrape_sharesansar_news(pages: int = 3) -> List[Dict]:
    """
    Scrape news headlines from ShareSansar.

    URL pattern: https://www.sharesansar.com/category/latest?page=N
    Uses similar HTML parsing approach.

    Returns list of dicts with keys: title, url, date_str, source
    """
    articles = []
    base_url = "https://www.sharesansar.com"

    for page in range(1, pages + 1):
        url = f"{base_url}/category/latest?page={page}"
        logger.info(f"Fetching ShareSansar page {page}/{pages}: {url}")
        html = _fetch_url(url)
        if not html:
            # Try alternative URL pattern
            url = f"{base_url}/category/latest/{page}"
            html = _fetch_url(url)
            if not html:
                continue

        # ShareSansar article links typically follow pattern:
        # <a href="https://www.sharesansar.com/newsdetail/SLUG-NNNN">TITLE</a>
        news_pattern = re.compile(
            r'<a[^>]*href="((?:https?://www\.sharesansar\.com)?/newsdetail/[^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        date_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'
        )

        matches = news_pattern.findall(html)
        dates = date_pattern.findall(html)

        for i, (href, title_raw) in enumerate(matches):
            title = unescape(re.sub(r'<[^>]+>', '', title_raw)).strip()
            if not title or len(title) < 10:
                continue

            full_url = href if href.startswith("http") else f"{base_url}{href}"
            date_str = dates[i] if i < len(dates) else ""

            articles.append({
                "title": title,
                "url": full_url,
                "date_str": date_str,
                "source": "sharesansar",
            })

        time.sleep(REQUEST_DELAY)

    logger.info(f"Scraped {len(articles)} articles from ShareSansar")
    return articles


# --- Sentiment Scoring ---

HF_MODELS = {
    "nepali-xlmr": ("AurevinP/xlm-roberta-base-nepali-sentiment-v1", "nepali-xlmr"),
    "fin-qwen": ("NOSIBLE/financial-sentiment-v1.2-base", "fin-qwen"),
    "xlm-roberta": ("cardiffnlp/twitter-xlm-roberta-base-sentiment", "xlm-roberta-base-sentiment"),
}

AUTO_MODEL_ORDER = ("xlm-roberta", "nepali-xlmr", "fin-qwen")


def _load_hf_classifier(model_id: str, short_name: str):
    """Load a HF sentiment pipeline. Returns (pipeline, short_name) or (None, None)."""
    try:
        from transformers import pipeline as hf_pipeline
        logger.info("Loading %s...", model_id)
        classifier = hf_pipeline(
            "sentiment-analysis",
            model=model_id,
            top_k=None,
            truncation=True,
            max_length=512,
        )
        logger.info("%s loaded", short_name)
        return classifier, short_name
    except Exception as e:
        logger.warning("Failed to load %s: %s", model_id, e)
        return None, None


def _load_xlm_roberta():
    """Back-compat: load cardiffnlp XLM-R."""
    model_id, short = HF_MODELS["xlm-roberta"]
    return _load_hf_classifier(model_id, short)


def _label_to_score(label_scores: Dict[str, float]) -> Dict:
    """Map classifier label probs to score/confidence/label on [-1, 1]."""
    # Normalize common label aliases
    normalized: Dict[str, float] = {}
    for raw, val in label_scores.items():
        key = raw.lower().replace(" ", "_").replace("-", "_")
        if key in ("label_2", "pos", "positive", "bullish", "very_positive"):
            normalized["positive"] = max(normalized.get("positive", 0.0), float(val))
        elif key in ("label_0", "neg", "negative", "bearish", "very_negative"):
            normalized["negative"] = max(normalized.get("negative", 0.0), float(val))
        elif key in ("label_1", "neu", "neutral"):
            normalized["neutral"] = max(normalized.get("neutral", 0.0), float(val))
        else:
            normalized[key] = float(val)

    pos = normalized.get("positive", 0.0)
    neg = normalized.get("negative", 0.0)
    neu = normalized.get("neutral", 0.0)
    score = pos - neg
    confidence = max(pos, neg, neu, 0.0) or max(label_scores.values(), default=0.0)
    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"
    return {
        "score": round(float(score), 4),
        "confidence": round(float(confidence), 4),
        "label": label,
    }


def score_with_xlm_roberta(texts: List[str], classifier) -> List[Dict]:
    """Score texts with a HF sentiment pipeline (any of the supported models)."""
    results = []
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            outputs = classifier(batch)
            for output in outputs:
                if isinstance(output, list):
                    label_scores = {item["label"].lower(): item["score"] for item in output}
                else:
                    label_scores = {output["label"].lower(): output["score"]}
                results.append(_label_to_score(label_scores))
        except Exception as e:
            logger.warning("HF batch scoring failed: %s", e)
            for text in batch:
                results.append(score_with_keywords(text))
    return results


def score_with_keywords(text: str) -> Dict:
    """
    Keyword-based sentiment scoring fallback.
    Returns dict with keys: score (-1 to +1), confidence (0-1), label
    """
    text_lower = text.lower()
    pos_count = sum(1 for kw in ALL_POSITIVE if kw.lower() in text_lower)
    neg_count = sum(1 for kw in ALL_NEGATIVE if kw.lower() in text_lower)

    total = pos_count + neg_count
    if total == 0:
        return {"score": 0.0, "confidence": 0.1, "label": "neutral"}

    score = (pos_count - neg_count) / total
    confidence = min(total / 5.0, 1.0)  # Scale confidence: 5+ keywords = 1.0

    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return {"score": round(score, 4), "confidence": round(confidence, 4), "label": label}


def parse_llm_sentiment_json(raw: str) -> Dict[str, Any]:
    """Parse Ollama JSON into tickers/event_type/sentiment/confidence. Pure helper for tests."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty LLM response")
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM JSON root is not an object")

    tickers_raw = data.get("tickers") or data.get("symbols") or []
    if isinstance(tickers_raw, str):
        tickers_raw = [t.strip() for t in tickers_raw.split(",") if t.strip()]
    tickers = [str(t).upper().strip() for t in tickers_raw if str(t).strip()]

    sentiment = str(data.get("sentiment") or data.get("label") or "neutral").lower().strip()
    if sentiment in ("pos", "bullish", "very_positive", "positive"):
        label, score = "positive", 0.7
    elif sentiment in ("neg", "bearish", "very_negative", "negative"):
        label, score = "negative", -0.7
    else:
        label, score = "neutral", 0.0

    if "score" in data:
        try:
            score = max(-1.0, min(1.0, float(data["score"])))
        except (TypeError, ValueError):
            pass
        label = "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral"

    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    event_type = str(data.get("event_type") or data.get("event") or "other").strip().lower() or "other"
    return {
        "tickers": tickers,
        "event_type": event_type,
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "label": label,
    }


def map_names_to_tickers(text: str, name_map: Dict[str, str]) -> List[str]:
    """Match company names inside text to tickers (longest name first)."""
    if not text or not name_map:
        return []
    lowered = text.lower()
    hits = []
    for name in sorted(name_map.keys(), key=len, reverse=True):
        if len(name) < 4:
            continue
        if name in lowered:
            hits.append(name_map[name])
    # de-dupe preserve order
    seen = set()
    out = []
    for t in hits:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def score_with_llm(
    articles: List[Dict],
    *,
    db_path: str,
    known_symbols: Optional[set] = None,
) -> Optional[List[Dict]]:
    """Score via Ollama. Returns None if Ollama unavailable (caller falls back)."""
    try:
        from backend.agents.llm_ollama import SUGGESTED_MODEL, call_ollama
    except Exception as e:
        logger.warning("Ollama client unavailable: %s", e)
        return None

    if known_symbols is None:
        known_symbols = _load_symbols_from_db(db_path)
    name_map = _load_name_to_symbol(db_path)
    # Compact name list for the prompt (cap size)
    sample_names = sorted(name_map.items(), key=lambda kv: len(kv[0]), reverse=True)[:80]
    name_hint = "; ".join(f"{name}={sym}" for name, sym in sample_names)

    system = (
        "You score NEPSE financial news. Reply with ONLY one JSON object: "
        '{"tickers":["SYM"],"event_type":"earnings|dividend|ipo|macro|other",'
        '"sentiment":"positive|neutral|negative","score":-1.0_to_1.0,"confidence":0.0_to_1.0}. '
        "Map company names to NEPSE tickers when possible."
    )
    results = []
    model_name = f"ollama-{SUGGESTED_MODEL}"
    for article in articles:
        title = article.get("title") or ""
        prompt = f"Known name→ticker samples: {name_hint}\n\nHeadline: {title}"
        raw = call_ollama(
            prompt,
            system=system,
            max_tokens=200,
            model=SUGGESTED_MODEL,
            purpose="chat",
            temperature=0.1,
        )
        if not raw or str(raw).startswith("ERROR:"):
            logger.warning("Ollama scoring failed: %s", raw)
            return None
        try:
            parsed = parse_llm_sentiment_json(str(raw))
        except (ValueError, json.JSONDecodeError) as e:
            logger.debug("LLM JSON parse failed (%s); keyword fallback for one article", e)
            parsed = {**score_with_keywords(title), "tickers": [], "event_type": "other"}

        tickers = list(parsed.get("tickers") or [])
        tickers.extend(_extract_symbols_from_text(title, known_symbols))
        tickers.extend(map_names_to_tickers(title, name_map))
        # keep only known symbols when we have a universe
        if known_symbols:
            tickers = [t for t in dict.fromkeys(tickers) if t in known_symbols]
        else:
            tickers = list(dict.fromkeys(tickers))

        results.append({
            "score": parsed["score"],
            "confidence": parsed["confidence"],
            "label": parsed["label"],
            "tickers": tickers,
            "event_type": parsed.get("event_type", "other"),
            "model_name": model_name,
        })
        time.sleep(0.05)
    return results


def _resolve_classifier(model: str):
    """Return (classifier, model_name) for HF path, or (None, 'keyword')."""
    if model == "keyword":
        return None, "keyword"
    keys = AUTO_MODEL_ORDER if model == "auto" else (model,)
    for key in keys:
        if key not in HF_MODELS:
            continue
        model_id, short = HF_MODELS[key]
        classifier, loaded = _load_hf_classifier(model_id, short)
        if classifier is not None:
            return classifier, loaded
        if model != "auto":
            break
    return None, "keyword"


def score_articles(
    articles: List[Dict],
    model: str = "auto",
    db_path: str = str(DEFAULT_DB_PATH),
) -> List[Dict]:
    """
    Score articles using the specified or best available model.

    model: auto | nepali-xlmr | fin-qwen | xlm-roberta | keyword | llm
    """
    if not articles:
        return []

    if model == "llm":
        llm_scores = score_with_llm(articles, db_path=db_path)
        if llm_scores is not None:
            for article, score_dict in zip(articles, llm_scores):
                article["sentiment_score"] = score_dict["score"]
                article["sentiment_confidence"] = score_dict["confidence"]
                article["sentiment_label"] = score_dict["label"]
                article["model_name"] = score_dict["model_name"]
                article["llm_tickers"] = score_dict.get("tickers") or []
                article["event_type"] = score_dict.get("event_type") or "other"
            return articles
        logger.warning("LLM scoring unavailable; falling back to auto classifier")
        model = "auto"

    classifier, model_name = _resolve_classifier(model)
    texts = [a["title"] for a in articles]

    if classifier is not None:
        logger.info("Scoring %s articles with %s", len(texts), model_name)
        scores = score_with_xlm_roberta(texts, classifier)
    else:
        logger.info("Scoring %s articles with keyword-based scorer", len(texts))
        model_name = "keyword"
        scores = [score_with_keywords(t) for t in texts]

    for article, score_dict in zip(articles, scores):
        article["sentiment_score"] = score_dict["score"]
        article["sentiment_confidence"] = score_dict["confidence"]
        article["sentiment_label"] = score_dict["label"]
        article["model_name"] = model_name

    return articles


# --- Aggregation and Storage ---

def _parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD (publication calendar day)."""
    if not date_str:
        return None

    formats = [
        "%b %d, %Y %I:%M %p",      # "Feb 13, 2026 05:55 PM"
        "%b %d, %Y",                # "May 01, 2018"
        "%Y-%m-%d %H:%M:%S",        # "2026-02-13 17:55:00"
        "%Y-%m-%d",                  # "2026-02-13"
        "%d %b %Y",                  # "13 Feb 2026"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _article_symbols(article: Dict, known_symbols: set, name_map: Dict[str, str]) -> List[str]:
    """Prefer LLM tickers; else regex tickers + company-name hits."""
    symbols: List[str] = []
    for sym in article.get("llm_tickers") or []:
        s = str(sym).upper().strip()
        if s and (not known_symbols or s in known_symbols):
            symbols.append(s)
    title = article.get("title") or ""
    symbols.extend(_extract_symbols_from_text(title, known_symbols))
    symbols.extend(map_names_to_tickers(title, name_map))
    return list(dict.fromkeys(symbols))


def aggregate_and_store(
    articles: List[Dict],
    db_path: str,
    known_symbols: Optional[set] = None,
):
    """
    Aggregate scored articles by (date, symbol, source) and store in DB.

    `date` is the article's published_at calendar day (from date_str) so the
    signal layer can enforce no look-ahead with date < trade_date.
    """
    if not articles:
        logger.warning("No articles to store")
        return 0

    if known_symbols is None:
        known_symbols = _load_symbols_from_db(db_path)
    name_map = _load_name_to_symbol(db_path)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now().strftime("%Y-%m-%d")

    from collections import defaultdict

    # key = (date, symbol_or_none, source, model)
    groups = defaultdict(lambda: {"scores": [], "confidences": []})

    for article in articles:
        published = _parse_date(article.get("date_str", ""))
        article["published_at"] = published or today
        date = article["published_at"]
        source = article.get("source", "unknown")
        model = article.get("model_name", "keyword")
        score = article.get("sentiment_score", 0.0)
        conf = article.get("sentiment_confidence", 0.0)

        # Market-wide entry (symbol = empty string for SQLite NULL handling)
        key = (date, "", source, model)
        groups[key]["scores"].append(score)
        groups[key]["confidences"].append(conf)

        for sym in _article_symbols(article, known_symbols, name_map):
            key = (date, sym, source, model)
            groups[key]["scores"].append(score)
            groups[key]["confidences"].append(conf)

    # Store aggregated scores
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    stored = 0

    for (date, symbol, source, model), data in groups.items():
        scores = data["scores"]
        confidences = data["confidences"]
        mean_score = sum(scores) / len(scores)
        mean_conf = sum(confidences) / len(confidences)
        n_docs = len(scores)

        # Use None for market-wide (no symbol)
        sym_value = symbol if symbol else None

        try:
            cursor.execute(
                """INSERT OR REPLACE INTO sentiment_scores
                   (date, symbol, source, model, score, confidence, n_documents, scraped_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, sym_value, source, model, round(mean_score, 4),
                 round(mean_conf, 4), n_docs, now_utc),
            )
            stored += 1
        except sqlite3.Error as e:
            logger.warning(f"Failed to store ({date}, {symbol}, {source}): {e}")

    conn.commit()
    conn.close()
    logger.info(f"Stored {stored} aggregated sentiment scores")
    return stored


# --- Main pipeline ---

def _sources_needing_scrape(db_path: str, sources: List[str], *, force: bool) -> List[str]:
    """Skip sources that already have today's sentiment_scores rows (unless force)."""
    if force:
        return list(sources)
    from backend.quant_pro.ingest_cache import has_rows, today_iso

    today = today_iso()
    needed = []
    for source in sources:
        if has_rows(
            db_path,
            "SELECT COUNT(*) FROM sentiment_scores WHERE date = ? AND source = ?",
            (today, source),
        ):
            logger.info("Skip %s scrape — sentiment_scores already has %s", source, today)
            continue
        needed.append(source)
    return needed


def run_sentiment_pipeline(
    pages: int = 3,
    model: str = "auto",
    db_path: str = str(DEFAULT_DB_PATH),
    sources: Optional[List[str]] = None,
    force: bool = False,
) -> int:
    """
    Full sentiment ingestion pipeline:
    1. Scrape news from MeroLagani and/or ShareSansar (skip source if today's scores exist)
    2. Score with NLP model (XLM-RoBERTa or keyword fallback)
    3. Aggregate and store in sentiment_scores table

    Args:
        pages: Number of pages to scrape per source
        model: auto | nepali-xlmr | fin-qwen | xlm-roberta | keyword | llm
        db_path: Path to SQLite database
        sources: List of sources to scrape ("merolagani", "sharesansar")
        force: Re-scrape even when today's scores already exist

    Returns: Number of aggregated scores stored
    """
    if sources is None:
        sources = ["merolagani", "sharesansar"]

    sources = _sources_needing_scrape(db_path, sources, force=force)
    if not sources:
        logger.info("All requested sources already cached for today (pass force=True to refresh)")
        return 0

    all_articles = []

    if "merolagani" in sources:
        ml_articles = scrape_merolagani_news(pages=pages)
        all_articles.extend(ml_articles)

    if "sharesansar" in sources:
        ss_articles = scrape_sharesansar_news(pages=pages)
        all_articles.extend(ss_articles)

    if not all_articles:
        logger.warning("No articles scraped from any source")
        return 0

    logger.info(f"Total articles scraped: {len(all_articles)}")

    # Score all articles
    scored_articles = score_articles(all_articles, model=model, db_path=db_path)

    # Log sentiment distribution
    scores = [a["sentiment_score"] for a in scored_articles]
    if scores:
        pos = sum(1 for s in scores if s > 0.1)
        neg = sum(1 for s in scores if s < -0.1)
        neu = len(scores) - pos - neg
        logger.info(f"Sentiment distribution: {pos} positive, {neg} negative, {neu} neutral")
        logger.info(f"Mean sentiment: {sum(scores)/len(scores):.4f}")

    # Aggregate and store
    stored = aggregate_and_store(scored_articles, db_path)
    return stored


def parse_merolagani_news_detail(html: str, news_id: int) -> Optional[Dict[str, Any]]:
    """Parse a Merolagani NewsDetail.aspx?newsID=<id> HTML page.

    Returns an article dict or None if missing/malformed (e.g. deleted ID or
    tampered proxy response).
    """
    if not html:
        return None
    title_match = re.search(
        r'id="ctl00_ContentPlaceHolder1_newsTitle"[^>]*>(.*?)</',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    date_match = re.search(
        r'id="ctl00_ContentPlaceHolder1_newsDate"[^>]*>(.*?)</',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not title_match or not date_match:
        return None
    title = unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip()
    date_str = unescape(re.sub(r"<[^>]+>", "", date_match.group(1))).strip()
    published = _parse_date(date_str)
    if not title or len(title) < 6 or not published:
        return None

    content = ""
    body_match = re.search(
        r'id="ctl00_ContentPlaceHolder1_newsDetail"[^>]*>(.*?)</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if body_match:
        content = unescape(re.sub(r"<[^>]+>", " ", body_match.group(1)))
        content = re.sub(r"\s+", " ", content).strip()[:500]

    return {
        "news_id": int(news_id),
        "title": title,
        "url": f"https://merolagani.com/NewsDetail.aspx?newsID={int(news_id)}",
        "date_str": date_str,
        "published_at": published,
        "content": content,
        "source": "merolagani",
    }


def _max_stored_merolagani_news_id(db_path: str) -> Optional[int]:
    try:
        conn = sqlite3.connect(db_path, timeout=60)
        try:
            rows = conn.execute(
                "SELECT url FROM news WHERE source = 'merolagani' AND url LIKE '%newsID=%'"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    best: Optional[int] = None
    for (url,) in rows:
        m = re.search(r"newsID=(\d+)", str(url or ""))
        if m:
            nid = int(m.group(1))
            if best is None or nid > best:
                best = nid
    return best


def _latest_merolagani_news_id(*, proxy_only: Optional[bool] = None) -> Optional[int]:
    html = _fetch_url("https://merolagani.com/NewsList.aspx?page=1", proxy_only=proxy_only)
    if not html:
        return None
    ids = [int(x) for x in re.findall(r"NewsDetail\.aspx\?newsID=(\d+)", html)]
    return max(ids) if ids else None


def _store_news_and_recompute_scores(
    articles: List[Dict[str, Any]],
    db_path: str,
    known_symbols: set,
    name_map: Dict[str, str],
) -> Tuple[int, int]:
    """Insert scored articles into ``news`` and recompute daily ``sentiment_scores``
    from all stored ``news`` rows for the touched dates (safe across batches)."""
    if not articles:
        return 0, 0
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    touched_dates: set[str] = set()
    news_rows = []
    model_used = articles[0].get("model_name", "keyword")
    source_used = articles[0].get("source", "merolagani")

    for a in articles:
        pub = a.get("published_at") or _parse_date(a.get("date_str", ""))
        if not pub:
            continue
        touched_dates.add(pub)
        syms = _article_symbols(a, known_symbols, name_map)
        primary_sym = syms[0] if syms else None
        news_rows.append(
            (
                primary_sym,
                pub,
                a["title"],
                a["url"],
                a.get("source", "merolagani"),
                round(float(a.get("sentiment_score", 0.0)), 4),
                a.get("sentiment_label", "neutral"),
                a.get("event_type", "general"),
                a.get("content", ""),
            )
        )

    if not news_rows:
        return 0, 0

    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    cur = conn.cursor()
    before = conn.total_changes
    cur.executemany(
        """
        INSERT OR IGNORE INTO news
            (symbol, date, headline, url, source, sentiment_score, sentiment_label, category, content)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        news_rows,
    )
    inserted_news = conn.total_changes - before

    # Recompute sentiment_scores across ALL stored news rows for touched dates
    from collections import defaultdict

    placeholders = ",".join("?" for _ in touched_dates)
    stored_rows = cur.execute(
        f"""
        SELECT date, headline, sentiment_score, symbol
        FROM news
        WHERE source = ? AND date IN ({placeholders}) AND sentiment_score IS NOT NULL
        """,
        [source_used, *sorted(touched_dates)],
    ).fetchall()

    groups = defaultdict(list)
    for pub_date, headline, s_score, primary_sym in stored_rows:
        score_f = float(s_score)
        groups[(pub_date, "")].append(score_f)
        mentioned = _article_symbols({"title": headline or ""}, known_symbols, name_map)
        if primary_sym and primary_sym not in mentioned:
            mentioned.append(primary_sym)
        for sym in mentioned:
            groups[(pub_date, sym)].append(score_f)

    agg_rows = []
    for (pub_date, sym), scs in groups.items():
        mean_s = sum(scs) / len(scs)
        agg_rows.append(
            (
                pub_date,
                sym if sym else None,
                source_used,
                model_used,
                round(mean_s, 4),
                round(min(1.0, abs(mean_s) + 0.5), 4),
                len(scs),
                now_utc,
            )
        )

    cur.executemany(
        """
        INSERT OR REPLACE INTO sentiment_scores
            (date, symbol, source, model, score, confidence, n_documents, scraped_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        agg_rows,
    )
    conn.commit()
    conn.close()
    return inserted_news, len(agg_rows)


def backfill_merolagani_news(
    *,
    start_id: int = 55000,
    end_id: Optional[int] = None,
    model: str = "xlm-roberta",
    db_path: str = str(DEFAULT_DB_PATH),
    batch_size: int = 64,
    rps: float = 1.0,
    proxy_only: Optional[bool] = None,
    force: bool = False,
) -> Dict[str, int]:
    """Walk Merolagani NewsDetail.aspx?newsID=<id>, store all articles in ``news``,
    and batch-score all articles with XLM-R into ``sentiment_scores``."""
    from backend.quant_pro.database import init_db

    init_db()
    if model == "llm":
        logger.warning("Backfill uses deterministic XLM-R, not LLM; switching model to auto")
        model = "auto"

    resume_from = int(start_id)
    if not force:
        max_stored = _max_stored_merolagani_news_id(db_path)
        if max_stored is not None and max_stored >= resume_from:
            resume_from = max_stored + 1
            logger.info("Resuming Merolagani news backfill from newsID=%d (max stored=%d)", resume_from, max_stored)

    if end_id is None:
        detected = _latest_merolagani_news_id(proxy_only=proxy_only)
        if detected is None:
            raise RuntimeError("Could not detect latest Merolagani newsID; pass --end-id explicitly")
        end_id = detected
        logger.info("Detected latest Merolagani newsID=%d", end_id)

    if resume_from > end_id:
        logger.info("News backfill already up to date (resume_from=%d > end_id=%d)", resume_from, end_id)
        return {"scanned": 0, "inserted": 0, "scores_updated": 0, "errors": 0}

    known_symbols = _load_symbols_from_db(db_path)
    name_map = _load_name_to_symbol(db_path)
    classifier, model_name = _resolve_classifier(model)
    if classifier is None:
        model_name = "keyword"
    logger.info(
        "Backfilling Merolagani newsID %d..%d (model=%s, batch=%d, rps=%.2f)",
        resume_from, end_id, model_name, batch_size, rps,
    )

    delay = 1.0 / max(float(rps or 1.0), 0.1)
    stats = {"scanned": 0, "inserted": 0, "scores_updated": 0, "errors": 0}
    buf: List[Dict[str, Any]] = []

    def flush() -> None:
        if not buf:
            return
        texts = [a["title"] for a in buf]
        if classifier is not None:
            scores = score_with_xlm_roberta(texts, classifier)
        else:
            scores = [score_with_keywords(t) for t in texts]
        for a, s in zip(buf, scores):
            a["sentiment_score"] = s["score"]
            a["sentiment_confidence"] = s["confidence"]
            a["sentiment_label"] = s["label"]
            a["model_name"] = model_name
        ins, upd = _store_news_and_recompute_scores(buf, db_path, known_symbols, name_map)
        stats["inserted"] += ins
        stats["scores_updated"] += upd
        logger.info(
            "Flushed batch up to newsID=%d (%s): +%d news, %d daily score rows",
            buf[-1]["news_id"], buf[-1]["published_at"], ins, upd,
        )
        buf.clear()

    for nid in range(resume_from, int(end_id) + 1):
        stats["scanned"] += 1
        url = f"https://merolagani.com/NewsDetail.aspx?newsID={nid}"
        try:
            html = _fetch_url(url, timeout=20, proxy_only=proxy_only)
        except Exception as exc:
            stats["errors"] += 1
            logger.warning("newsID=%d fetch failed: %s", nid, exc)
            time.sleep(delay)
            continue

        article = parse_merolagani_news_detail(html, nid)
        if article is not None:
            buf.append(article)
            if len(buf) >= batch_size:
                flush()
        time.sleep(delay)

    flush()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Scrape NEPSE news and compute sentiment scores"
    )
    parser.add_argument(
        "--pages", type=int, default=3,
        help="Number of pages to scrape per source (default: 3)"
    )
    parser.add_argument(
        "--model",
        choices=["auto", "nepali-xlmr", "fin-qwen", "xlm-roberta", "keyword", "llm"],
        default="auto",
        help="Sentiment model (default: auto = nepali-xlmr → fin-qwen → xlm-roberta → keyword)",
    )
    parser.add_argument(
        "--db", type=str, default=str(DEFAULT_DB_PATH),
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--sources", nargs="+", default=["merolagani", "sharesansar"],
        choices=["merolagani", "sharesansar"],
        help="News sources to scrape"
    )
    parser.add_argument(
        "--keyword-only", action="store_true",
        help="Force keyword-based scoring (skip model download)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-scrape even when today's sentiment_scores already exist",
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="Walk historical Merolagani newsIDs and backfill news + sentiment_scores",
    )
    parser.add_argument(
        "--start-id", type=int, default=55000,
        help="Starting Merolagani newsID for --backfill (default: 55000 ≈ early 2020)",
    )
    parser.add_argument(
        "--end-id", type=int, default=None,
        help="Ending Merolagani newsID for --backfill (default: auto-detect latest)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=64,
        help="XLM-R scoring batch size for --backfill (default: 64)",
    )
    parser.add_argument(
        "--rps", type=float, default=1.0,
        help="Requests per second for --backfill (default: 1.0)",
    )
    parser.add_argument(
        "--proxy-only", action="store_true",
        help="Route all scraping via free proxies only (never direct IP)",
    )

    args = parser.parse_args()

    if args.proxy_only:
        os.environ["NQT_PROXY_ONLY"] = "1"

    model = "keyword" if args.keyword_only else args.model

    if args.backfill:
        stats = backfill_merolagani_news(
            start_id=args.start_id,
            end_id=args.end_id,
            model=model,
            db_path=args.db,
            batch_size=args.batch_size,
            rps=args.rps,
            proxy_only=True if args.proxy_only else None,
            force=args.force,
        )
        print(f"\nBackfill done: {stats}")
        return 0

    stored = run_sentiment_pipeline(
        pages=args.pages,
        model=model,
        db_path=args.db,
        sources=args.sources,
        force=args.force,
    )
    print(f"\nDone. Stored {stored} aggregated sentiment scores.")
    return 0 if stored > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
