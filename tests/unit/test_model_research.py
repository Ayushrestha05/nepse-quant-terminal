from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from backend.quant_pro.model_research import (
    _candidate_outcome,
    _collect_candidates,
    _feature_row,
    _training_rows_for_fold,
)


def _cache(frame):
    return {"AAA": (frame, frame["date"].to_numpy(dtype="datetime64[ns]"))}


def test_features_ignore_prices_after_signal_date():
    dates = pd.date_range("2025-01-01", periods=70, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": np.linspace(100, 140, len(dates)),
            "high": np.linspace(101, 141, len(dates)),
            "low": np.linspace(99, 139, len(dates)),
            "close": np.linspace(100, 140, len(dates)),
            "volume": np.linspace(1000, 2000, len(dates)),
        }
    )
    candidate = {
        "symbol": "AAA",
        "strength": 0.7,
        "confidence": 0.8,
        "raw_score": 0.56,
        "support_count": 1,
        "signal_type": "momentum",
    }
    signal_day = dates[40]
    before = _feature_row(candidate, _cache(frame), signal_day, "bull")
    changed = frame.copy()
    changed.loc[changed["date"] > signal_day, ["close", "volume"]] *= 50
    after = _feature_row(candidate, _cache(changed), signal_day, "bull")

    assert before == after


def test_candidate_label_includes_fees_and_slippage():
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [100, 100, 100, 100, 100],
            "high": [100, 101, 103, 106, 100],
            "low": [100, 99, 99, 99, 100],
            "close": [100, 100, 102, 105, 100],
            "volume": [1000] * 5,
        }
    )
    args = (_cache(frame), "AAA", list(dates), 0, 2, 1_000_000, 1)
    no_slippage = _candidate_outcome(*args, 0.0)
    high_slippage = _candidate_outcome(*args, 0.05)

    assert no_slippage["label"] == 1
    assert high_slippage["label"] == 0
    assert high_slippage["net_return_pct"] < no_slippage["net_return_pct"]


def test_fold_training_excludes_outcomes_unknown_at_test_start():
    rows = [
        {"date_index": 4, "exit_index": 8, "label": 1},
        {"date_index": 5, "exit_index": 10, "label": 0},
        {"date_index": 6, "exit_index": 9, "label": 1},
        {"date_index": 6, "exit_index": 9},
        {"date_index": 7, "exit_index": 12, "label": 0},
    ]

    assert _training_rows_for_fold(rows, cursor=10, training_days=6) == [rows[0], rows[2]]


def test_unlabeled_candidate_is_kept_for_out_of_sample_ranking():
    dates = pd.date_range("2025-01-01", periods=2, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [100, 100],
            "high": [101, 101],
            "low": [99, 99],
            "close": [100, 100],
            "volume": [1000, 1000],
        }
    )
    signal = SimpleNamespace(
        symbol="AAA",
        signal_type=SimpleNamespace(value="momentum"),
        strength=0.8,
        confidence=0.8,
        reasoning="test",
    )
    records = []
    observer = _collect_candidates(
        records,
        holding_days=2,
        capital=1_000_000,
        max_positions=5,
        slippage_pct=0.005,
    )
    observer(
        dates[1],
        [signal],
        symbol_cache=_cache(frame),
        trading_dates=list(dates),
        date_index=1,
        regime="bull",
    )

    assert len(records) == 1
    assert records[0]["symbol"] == "AAA"
    assert "label" not in records[0]
