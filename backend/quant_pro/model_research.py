"""Rolling out-of-sample research for an open-source signal ranker."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.backtesting.simple_backtest import (
    BacktestResult,
    apply_circuit_breaker,
    get_symbol_history,
    run_backtest,
)
from backend.quant_pro.database import get_db_path
from backend.quant_pro.signal_ranking import merge_signal_candidates
from validation.transaction_costs import TransactionCostModel as NepseFees

FEATURE_KEYS = (
    "strength",
    "confidence",
    "raw_score",
    "support_count",
    "return_20d",
    "return_60d",
    "volatility_20d",
    "volume_ratio_20d",
    "signal_type",
    "regime",
)


@dataclass
class ModelResearchResult:
    baseline: BacktestResult
    model: BacktestResult
    folds: List[Dict[str, Any]]
    predictions: List[Dict[str, Any]]
    nepse_curve: List[Tuple[str, float]]
    settings: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "settings": self.settings,
            "baseline": _portfolio_metrics(self.baseline),
            "model": _portfolio_metrics(self.model),
            "folds": self.folds,
            "predictions": self.predictions,
            "baseline_trades": _trade_records(self.baseline),
            "model_trades": _trade_records(self.model),
            "baseline_curve": _curve(self.baseline),
            "model_curve": _curve(self.model),
            "nepse_curve": self.nepse_curve,
        }


def _feature_row(candidate: Dict[str, Any], symbol_cache: dict, day: pd.Timestamp, regime: str) -> Dict[str, Any]:
    history = get_symbol_history(symbol_cache, candidate["symbol"], day, tail=61)
    features: Dict[str, Any] = {
        "strength": float(candidate["strength"]),
        "confidence": float(candidate["confidence"]),
        "raw_score": float(candidate["raw_score"]),
        "support_count": float(candidate["support_count"]),
        "signal_type": str(candidate["signal_type"]),
        "regime": str(regime),
    }
    if history is None or len(history) < 2:
        features.update(return_20d=0.0, return_60d=0.0, volatility_20d=0.0, volume_ratio_20d=0.0)
        return features

    closes = pd.to_numeric(history["close"], errors="coerce").to_numpy(dtype=float)
    volumes = pd.to_numeric(history["volume"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    features["return_20d"] = float(closes[-1] / closes[-21] - 1.0) if len(closes) >= 21 and closes[-21] else 0.0
    features["return_60d"] = float(closes[-1] / closes[-61] - 1.0) if len(closes) >= 61 and closes[-61] else 0.0
    returns = pd.Series(closes).pct_change(fill_method=None).dropna().tail(20)
    volatility = float(returns.std(ddof=0)) if len(returns) else 0.0
    features["volatility_20d"] = volatility if math.isfinite(volatility) else 0.0
    mean_volume = float(np.mean(volumes[-21:-1])) if len(volumes) > 1 else 0.0
    ratio = float(volumes[-1] / mean_volume) if mean_volume > 0 else 0.0
    features["volume_ratio_20d"] = ratio if math.isfinite(ratio) else 0.0
    return features


def _price_row(symbol_cache: dict, symbol: str, day: pd.Timestamp) -> Optional[Tuple[pd.Series, Optional[float]]]:
    cached = symbol_cache.get(symbol)
    if cached is None:
        return None
    frame, dates = cached
    index = int(np.searchsorted(dates, np.datetime64(day), side="left"))
    if index >= len(dates) or pd.Timestamp(dates[index]) != day:
        return None
    previous_close = float(frame.iloc[index - 1]["close"]) if index > 0 else None
    return frame.iloc[index], previous_close


def _candidate_outcome(
    symbol_cache: dict,
    symbol: str,
    trading_dates: List[Any],
    signal_index: int,
    holding_days: int,
    capital: float,
    max_positions: int,
    slippage_pct: float,
) -> Optional[Dict[str, Any]]:
    entry_index = signal_index + 1
    exit_index = entry_index + holding_days
    if exit_index >= len(trading_dates):
        return None
    entry_date = pd.Timestamp(trading_dates[entry_index])
    exit_date = pd.Timestamp(trading_dates[exit_index])
    entry_row = _price_row(symbol_cache, symbol, entry_date)
    exit_row = _price_row(symbol_cache, symbol, exit_date)
    if entry_row is None or exit_row is None:
        return None

    entry_market, entry_previous_close = entry_row
    exit_market, exit_previous_close = exit_row
    entry_price = float(entry_market["open"])
    exit_price = float(exit_market["close"])
    if entry_previous_close is not None:
        entry_price = apply_circuit_breaker(entry_price, entry_previous_close)
    if exit_previous_close is not None:
        exit_price = apply_circuit_breaker(exit_price, exit_previous_close)
    entry_price *= 1.0 + slippage_pct
    exit_price *= 1.0 - slippage_pct
    if not math.isfinite(entry_price) or not math.isfinite(exit_price) or entry_price <= 0:
        return None

    shares = int((capital / max_positions) / entry_price)
    if shares < 10:
        return None
    buy_fees = NepseFees.total_fees(shares, entry_price)
    sell_fees = NepseFees.total_fees(shares, exit_price, is_sell=True)
    net_pnl = shares * (exit_price - entry_price) - buy_fees - sell_fees
    return {
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "exit_date": exit_date.strftime("%Y-%m-%d"),
        "exit_index": exit_index,
        "net_return_pct": float(net_pnl / (shares * entry_price + buy_fees) * 100.0),
        "label": int(net_pnl > 0),
    }


def _collect_candidates(
    records: List[Dict[str, Any]],
    *,
    holding_days: int,
    capital: float,
    max_positions: int,
    slippage_pct: float,
) -> Callable[..., None]:
    def observe(day, signals, *, symbol_cache, trading_dates, date_index, regime, **_kwargs):
        if not signals:
            return
        signal_rows = [
            {
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "strength": signal.strength,
                "confidence": signal.confidence,
                "reasoning": signal.reasoning,
            }
            for signal in signals
        ]
        date = pd.Timestamp(day)
        for candidate in merge_signal_candidates(signal_rows):
            outcome = _candidate_outcome(
                symbol_cache,
                candidate["symbol"],
                trading_dates,
                int(date_index),
                holding_days,
                capital,
                max_positions,
                slippage_pct,
            )
            records.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "symbol": candidate["symbol"],
                    "date_index": int(date_index),
                    "features": _feature_row(candidate, symbol_cache, date, regime),
                    **(outcome or {}),
                }
            )

    return observe


def _fit_classifier(rows: List[Dict[str, Any]]):
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        DictVectorizer(),
        StandardScaler(with_mean=False),
        LogisticRegression(max_iter=200, random_state=0),
    ).fit([row["features"] for row in rows], [row["label"] for row in rows])


def _training_rows_for_fold(records: List[Dict[str, Any]], cursor: int, training_days: int):
    start = max(0, cursor - training_days)
    return [
        row for row in records
        if start <= row["date_index"] < cursor
        and row.get("label") is not None
        and row.get("exit_index", cursor) < cursor
    ]


def _curve(result: BacktestResult) -> List[List[Any]]:
    if not result.daily_nav:
        return []
    initial = float(result.daily_nav[0][1]) or 1.0
    return [[pd.Timestamp(day).strftime("%Y-%m-%d"), float(nav) / initial] for day, nav in result.daily_nav]


def _portfolio_metrics(result: BacktestResult) -> Dict[str, Any]:
    profit_factor = result.profit_factor
    return {
        "total_return_pct": result.total_return * 100.0,
        "annualized_return_pct": result.annualized_return * 100.0,
        "max_drawdown_pct": result.max_drawdown * 100.0,
        "win_rate_pct": result.win_rate * 100.0,
        "profit_factor": profit_factor if math.isfinite(profit_factor) else None,
        "trade_count": result.total_trades,
        "total_pnl": result.total_pnl,
        "total_fees": result.total_fees_paid,
        "sharpe": result.sharpe_ratio,
    }


def _trade_records(result: BacktestResult) -> List[Dict[str, Any]]:
    return [
        {
            "symbol": trade.symbol,
            "signal_date": pd.Timestamp(trade.signal_date).strftime("%Y-%m-%d") if trade.signal_date else "",
            "entry_date": pd.Timestamp(trade.entry_date).strftime("%Y-%m-%d") if trade.entry_date else "",
            "entry_price": float(trade.entry_price),
            "exit_date": pd.Timestamp(trade.exit_date).strftime("%Y-%m-%d") if trade.exit_date else "",
            "exit_price": float(trade.exit_price) if trade.exit_price is not None else None,
            "shares": int(trade.shares),
            "net_pnl": float(trade.net_pnl or 0.0),
            "net_return_pct": float(trade.net_return or 0.0) * 100.0,
            "signal_type": str(trade.signal_type),
            "exit_reason": str(trade.exit_reason),
        }
        for trade in result.completed_trades
    ]


def _nepse_curve(start_date: str, end_date: str) -> List[Tuple[str, float]]:
    with sqlite3.connect(str(get_db_path())) as conn:
        rows = conn.execute(
            "SELECT date, close FROM stock_prices WHERE symbol='NEPSE' AND date BETWEEN ? AND ? ORDER BY date",
            (start_date, end_date),
        ).fetchall()
    if not rows or not float(rows[0][1]):
        return []
    first = float(rows[0][1])
    return [(str(day)[:10], float(close) / first) for day, close in rows]


def run_model_research(
    start_date: str,
    end_date: str,
    strategy_config: Dict[str, Any],
    *,
    training_days: int = 504,
    test_days: int = 63,
    slippage_pct: float = 0.005,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Any = None,
) -> ModelResearchResult:
    """Compare a rolling logistic ranker with the unchanged configured strategy."""
    if training_days < 60 or test_days < 1:
        raise ValueError("training_days must be at least 60 and test_days must be positive")
    if not math.isfinite(float(slippage_pct)) or not 0.0 <= float(slippage_pct) <= 0.05:
        raise ValueError("slippage_pct must be between 0 and 0.05 (5%)")
    config = dict(strategy_config or {})
    capital = float(config.get("initial_capital", 1_000_000))
    max_positions = int(config.get("max_positions", 5))
    holding_days = int(config.get("holding_days", 40))
    if capital <= 0 or max_positions < 1 or holding_days < 1:
        raise ValueError("strategy capital, max_positions, and holding_days must be positive")

    records: List[Dict[str, Any]] = []

    def report(stage: str, payload: Dict[str, Any]) -> None:
        if progress_callback:
            progress_callback({**payload, "stage": stage})

    def progress(stage: str):
        def callback(payload):
            pct = float(payload.get("progress_pct", 0))
            offset, scale = {
                "baseline": (0, 0.50),
                "baseline_oos": (50, 0.25),
                "model": (75, 0.25),
            }[stage]
            report(stage, {**payload, "progress_pct": int(offset + pct * scale)})
        return callback

    candidate_history = run_backtest(
        start_date,
        end_date,
        **config,
        candidate_observer=_collect_candidates(
            records,
            holding_days=holding_days,
            capital=capital,
            max_positions=max_positions,
            slippage_pct=float(slippage_pct),
        ),
        slippage_pct=float(slippage_pct),
        progress_callback=progress("baseline"),
        cancel_event=cancel_event,
    )
    trading_dates = [pd.Timestamp(day) for day, _ in candidate_history.daily_nav]
    if len(trading_dates) <= training_days:
        raise ValueError(f"Need more than {training_days} trading days; found {len(trading_dates)}")
    oos_start_date = trading_dates[training_days].strftime("%Y-%m-%d")
    del candidate_history

    score_overrides: Dict[Tuple[str, str], float] = {}
    predictions: List[Dict[str, Any]] = []
    folds: List[Dict[str, Any]] = []
    fold_bounds: List[Tuple[int, int]] = []
    cursor = training_days
    while cursor < len(trading_dates):
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Model research cancelled")
        fold_end = min(cursor + test_days, len(trading_dates))
        test_start = trading_dates[cursor]
        train_start = trading_dates[max(0, cursor - training_days)]
        train_rows = _training_rows_for_fold(records, cursor, training_days)
        if len(train_rows) < 50 or len({row["label"] for row in train_rows}) < 2:
            raise ValueError(
                f"Insufficient labeled trades before {test_start:%Y-%m-%d} "
                f"({len(train_rows)} samples); choose a longer history"
            )
        model = _fit_classifier(train_rows)
        test_rows = [row for row in records if cursor <= row["date_index"] < fold_end]
        if test_rows:
            probabilities = model.predict_proba([row["features"] for row in test_rows])
            class_index = list(model[-1].classes_).index(1)
            predicted = probabilities[:, class_index]
            for row, probability in zip(test_rows, predicted):
                probability = float(probability)
                score_overrides[(row["date"], row["symbol"])] = probability
                predictions.append(
                    {
                        "date": row["date"],
                        "symbol": row["symbol"],
                        "probability": probability,
                        "profitable": int(row["label"]) if row.get("label") is not None else None,
                        "signal_type": row["features"]["signal_type"],
                    }
                )
            labeled_predictions = [
                (row, float(probability)) for row, probability in zip(test_rows, predicted)
                if row.get("label") is not None
            ]
            correct = sum((probability >= 0.5) == bool(row["label"]) for row, probability in labeled_predictions)
            brier = (
                float(np.mean([(probability - row["label"]) ** 2 for row, probability in labeled_predictions]))
                if labeled_predictions else 0.0
            )
            hit_rate = correct / len(labeled_predictions) if labeled_predictions else 0.0
        else:
            hit_rate = 0.0
            brier = 0.0
        fold_bounds.append((cursor, fold_end))
        folds.append(
            {
                "train_start": train_start.strftime("%Y-%m-%d"),
                "test_start": test_start.strftime("%Y-%m-%d"),
                "test_end": trading_dates[fold_end - 1].strftime("%Y-%m-%d"),
                "train_candidates": len(train_rows),
                "test_candidates": len(test_rows),
                "matured_test_outcomes": len(labeled_predictions) if test_rows else 0,
                "candidate_hit_rate_pct": hit_rate * 100.0,
                "brier_score": brier,
            }
        )
        cursor = fold_end

    baseline_result = run_backtest(
        oos_start_date,
        end_date,
        **config,
        slippage_pct=float(slippage_pct),
        progress_callback=progress("baseline_oos"),
        cancel_event=cancel_event,
    )
    model_result = run_backtest(
        oos_start_date,
        end_date,
        **config,
        candidate_score_overrides=score_overrides,
        require_candidate_score=True,
        slippage_pct=float(slippage_pct),
        progress_callback=progress("model"),
        cancel_event=cancel_event,
    )

    for fold, (fold_start, fold_end) in zip(folds, fold_bounds):
        start = trading_dates[fold_start]
        end = trading_dates[fold_end - 1]
        for name, result in (("baseline", baseline_result), ("model", model_result)):
            navs = [(pd.Timestamp(day), float(nav)) for day, nav in result.daily_nav]
            window_nav = [nav for day, nav in navs if start <= day <= end]
            trades = [
                trade for trade in result.completed_trades
                if trade.signal_date is not None and start <= pd.Timestamp(trade.signal_date) <= end
            ]
            returns = [float(trade.net_pnl or 0.0) for trade in trades]
            wins = sum(value > 0 for value in returns)
            gross_wins = sum(value for value in returns if value > 0)
            gross_losses = abs(sum(value for value in returns if value <= 0))
            fold[f"{name}_return_pct"] = (
                (window_nav[-1] / window_nav[0] - 1.0) * 100.0 if len(window_nav) > 1 and window_nav[0] else 0.0
            )
            fold[f"{name}_trades"] = len(trades)
            fold[f"{name}_win_rate_pct"] = wins / len(trades) * 100.0 if trades else 0.0
            fold[f"{name}_profit_factor"] = gross_wins / gross_losses if gross_losses else None

    report("complete", {"progress_pct": 100, "message": "Research run complete"})
    return ModelResearchResult(
        baseline=baseline_result,
        model=model_result,
        folds=folds,
        predictions=predictions,
        nepse_curve=_nepse_curve(oos_start_date, end_date),
        settings={
            "start_date": start_date,
            "out_of_sample_start_date": oos_start_date,
            "end_date": end_date,
            "training_days": training_days,
            "test_days": test_days,
            "holding_days": holding_days,
            "slippage_pct": float(slippage_pct),
            "capital": capital,
            "max_positions": max_positions,
            "features": list(FEATURE_KEYS),
            "model": "scikit-learn LogisticRegression",
        },
    )
