"""Unit checks for LLM sentiment JSON parsing and ticker name mapping."""

from __future__ import annotations

from backend.quant_pro.data_scrapers.sentiment_ingestion import (
    map_names_to_tickers,
    parse_llm_sentiment_json,
)


def test_parse_llm_sentiment_json_plain():
    raw = '{"tickers":["NABIL","SBL"],"event_type":"dividend","sentiment":"positive","score":0.8,"confidence":0.7}'
    parsed = parse_llm_sentiment_json(raw)
    assert parsed["tickers"] == ["NABIL", "SBL"]
    assert parsed["event_type"] == "dividend"
    assert parsed["label"] == "positive"
    assert parsed["score"] == 0.8
    assert parsed["confidence"] == 0.7


def test_parse_llm_sentiment_json_fenced_and_negative():
    raw = """Here you go:
```json
{"tickers": "HBL", "event_type": "earnings", "sentiment": "bearish", "confidence": 0.9}
```
"""
    parsed = parse_llm_sentiment_json(raw)
    assert parsed["tickers"] == ["HBL"]
    assert parsed["label"] == "negative"
    assert parsed["score"] < 0
    assert parsed["event_type"] == "earnings"


def test_map_names_to_tickers_longest_first():
    name_map = {
        "nabil bank limited": "NABIL",
        "nabil bank": "NABIL",
        "himalayan bank limited": "HBL",
    }
    text = "Nabil Bank Limited declares bonus; Himalayan Bank Limited silent"
    # Longest names matched first → Himalayan before Nabil
    assert map_names_to_tickers(text, name_map) == ["HBL", "NABIL"]
