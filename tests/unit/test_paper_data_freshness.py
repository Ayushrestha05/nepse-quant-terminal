from datetime import datetime

import pandas as pd

from backend.trading import tui_trading_engine as engine_module


def _prices(benchmark="2026-04-09", candidate="2026-04-09"):
    return pd.DataFrame([
        {"symbol": "AAA", "date": pd.Timestamp(candidate), "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
        {"symbol": "NEPSE", "date": pd.Timestamp(benchmark), "open": 2700, "high": 2700, "low": 2700, "close": 2700, "volume": 1},
    ])


def _engine(frame, monkeypatch):
    engine = object.__new__(engine_module.TUITradingEngine)
    engine._prices_df = frame
    engine.logs = []
    engine._log = engine.logs.append
    engine.max_positions = 5
    engine.positions = {}
    monkeypatch.setattr(engine_module, "now_nst", lambda: datetime(2026, 4, 10, 12))
    monkeypatch.setattr(engine_module, "open_issue_symbols", lambda _operation: set())
    return engine


def test_stale_benchmark_pauses_paper_buys(monkeypatch):
    engine = _engine(_prices(benchmark="2026-04-08"), monkeypatch)

    engine._execute_buys([{"symbol": "AAA"}])

    assert any("BUY PAUSED" in line and "NEPSE completed bar" in line for line in engine.logs)


def test_unresolved_benchmark_issue_pauses_paper_buys(monkeypatch):
    engine = _engine(_prices(), monkeypatch)
    monkeypatch.setattr(engine_module, "open_issue_symbols", lambda _operation: {"NEPSE"})

    ready, reason = engine._buy_data_readiness()

    assert not ready
    assert "unresolved" in reason


def test_stale_candidate_session_is_removed_from_generated_signals(monkeypatch):
    engine = _engine(_prices(candidate="2026-04-08"), monkeypatch)
    engine.signal_types = ["momentum"]
    engine.account_id = "test"
    engine.strategy_config = {}
    engine.max_positions = 5
    engine.holding_days = 40
    engine.sector_limit = 0.35
    engine._active_run_id = ""
    engine._paper_execution = type("Manifest", (), {"start_strategy_manifest": lambda *_args, **_kwargs: None})()
    monkeypatch.setattr(engine_module, "load_shared_price_history", lambda _path: engine._prices_df)
    monkeypatch.setattr(engine_module, "generate_signals", lambda *_args, **_kwargs: ([{"symbol": "AAA"}], "neutral"))

    engine._generate_signals()

    assert engine.signals_today == []
    assert any("BUY PAUSED AAA" in line for line in engine.logs)
