import sqlite3
from datetime import date, datetime, timezone
import pandas as pd

from apps.desktop import stock_detail


def _history(count=130):
    dates = pd.date_range("2026-01-01", periods=count, freq="D").strftime("%Y-%m-%d")
    close = [100.0 + index for index in range(count)]
    return pd.DataFrame({
        "date": dates,
        "open": [value - 1 for value in close],
        "high": [value + 2 for value in close],
        "low": [value - 2 for value in close],
        "close": close,
        "volume": [1000 + index for index in range(count)],
    })


def test_history_ranges_keep_moving_averages_calculated_before_filtering():
    history = _history()
    month = stock_detail.prepare_history(history, "1M")
    year = stock_detail.prepare_history(history, "1Y")
    all_rows = stock_detail.prepare_history(history, "All")

    assert 28 <= len(month) <= 32
    assert len(year) == len(history)
    assert len(all_rows) == len(history)
    first_index = history.date.tolist().index(month.iloc[0].date)
    assert month.iloc[0].ma20 == history.close.iloc[first_index - 19:first_index + 1].mean()
    assert month.iloc[-1].ma50 == history.close.tail(50).mean()


def test_sparse_history_omits_daily_change_and_reports_incomplete_coverage(monkeypatch):
    history = _history(2)
    history.loc[1, "date"] = "2026-02-01"
    monkeypatch.setattr("backend.quant_pro.nepse_calendar.latest_completed_session", lambda: date(2026, 2, 2))

    metrics = stock_detail.market_metrics(history, None)

    assert metrics["change"] == "—"
    assert "gap" in metrics["coverage"]
    assert metrics["range"].startswith("103.00 / 98.00")


def test_market_metrics_keep_quote_and_history_dates_distinct(monkeypatch):
    history = _history(2)
    monkeypatch.setattr("backend.quant_pro.nepse_calendar.latest_completed_session", lambda: date(2026, 1, 3))

    metrics = stock_detail.market_metrics(history, {
        "last_traded_price": 333.25,
        "fetched_at_utc": "2026-01-03T09:00:00+00:00",
    })

    assert "333.25" in metrics["quote"]
    assert "UTC" in metrics["quote"]
    assert "2026-01-02" in metrics["historical"]
    assert metrics["change"].startswith("+1.00%")
    assert "Open 100.00" in metrics["session"] and "Volume 1,001" in metrics["session"]


def test_market_metrics_flag_an_old_cached_quote(monkeypatch):
    monkeypatch.setattr("backend.quant_pro.nepse_calendar.latest_completed_session", lambda: date(2026, 1, 2))
    metrics = stock_detail.market_metrics(
        _history(2),
        {"last_traded_price": 101, "fetched_at_utc": "2026-01-02T09:00:00Z"},
        now=datetime(2026, 1, 6, tzinfo=timezone.utc),
    )

    assert "cached quote is stale" in metrics["coverage"]


def test_detail_loader_uses_symbol_parameters_and_keeps_report_optional(tmp_path, monkeypatch):
    path = tmp_path / "market.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE stock_prices (symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    conn.execute("CREATE TABLE market_quotes (symbol TEXT,security_name TEXT,last_traded_price REAL,previous_close REAL,percentage_change REAL,fetched_at_utc TEXT)")
    conn.execute("INSERT INTO stock_prices VALUES (?,?,?,?,?,?,?)", ("ODD'CODE", "2026-10-01", 10, 12, 9, 11, 100))
    conn.execute("INSERT INTO market_quotes VALUES (?,?,?,?,?,?)", ("ODD'CODE", "Odd Company", 11.5, 11, 4.5, "2026-10-01T10:00:00Z"))
    conn.commit()
    conn.close()

    def unavailable(*_args):
        raise RuntimeError("financial cache unavailable")

    monkeypatch.setattr("backend.quant_pro.stock_report.build_stock_report", unavailable)
    payload = stock_detail.load_stock_detail("ODD'CODE", path)

    assert payload["history"].iloc[0]["close"] == 11
    assert payload["quote"]["security_name"] == "Odd Company"
    assert payload["report"] is None
    assert "financial cache unavailable" in payload["report_error"]


def test_chart_draws_candles_and_line_with_volume():
    from matplotlib.figure import Figure

    history = stock_detail.prepare_history(_history(60), "3M")
    figure = Figure()
    stock_detail.draw_price_chart(figure, history)
    candle_axes = figure.axes[0]
    assert len(candle_axes.patches) == len(history)
    assert len(figure.axes) == 2

    stock_detail.draw_price_chart(figure, history, line=True)
    assert figure.axes[0].lines[0].get_label() == "Close"
    assert len(figure.axes) == 2


def test_stock_window_discards_stale_requests_and_closed_results():
    window = stock_detail.StockDetailWindow.__new__(stock_detail.StockDetailWindow)
    loads = []
    rendered = []
    changes = []

    class Value:
        def set(self, _value):
            pass

    class FakeWindow:
        def deiconify(self):
            pass

        def lift(self):
            pass

        def focus_set(self):
            pass

        def destroy(self):
            pass

    window.parent = None
    window.load = lambda symbol, done: loads.append((symbol, done))
    window.on_close = lambda: changes.append("closed")
    window.closed = False
    window.request_id = 0
    window.request_running = False
    window.symbol = ""
    window.payload = None
    window.title = Value()
    window.window = FakeWindow()
    window.render = lambda: rendered.append(window.payload["symbol"])

    window.select("AAA")
    window.select("BBB")
    assert [symbol for symbol, _done in loads] == ["AAA"]
    loads[0][1]({"symbol": "AAA"})
    assert [symbol for symbol, _done in loads] == ["AAA", "BBB"]
    loads[1][1]({"symbol": "BBB"})
    assert rendered == ["BBB"]

    window.select("CCC")
    window.close()
    loads[2][1]({"symbol": "CCC"})
    assert rendered == ["BBB"]
    assert changes == ["closed"]
