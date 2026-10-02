import sqlite3

from backend.backtesting import simple_backtest


def test_price_history_is_loaded_once_and_refreshes_only_changed_symbols(tmp_path, monkeypatch):
    db_path = tmp_path / "prices.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE stock_prices(symbol,date,open,high,low,close,volume)")
    conn.executemany(
        "INSERT INTO stock_prices VALUES(?,?,?,?,?,?,?)",
        [
            ("AAA", "2026-10-01", 10, 10, 10, 10, 1),
            ("BBB", "2026-10-01", 20, 20, 20, 20, 1),
        ],
    )
    conn.commit()
    conn.close()

    original = simple_backtest.load_all_prices
    calls = 0

    def counted(connection):
        nonlocal calls
        calls += 1
        return original(connection)

    monkeypatch.setattr(simple_backtest, "load_all_prices", counted)
    first = simple_backtest.load_shared_price_history(db_path)
    assert simple_backtest.load_shared_price_history(db_path) is first
    assert calls == 1

    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO stock_prices VALUES('AAA','2026-10-02',11,11,11,11,2)")
    conn.execute("INSERT INTO stock_prices VALUES('BBB','2026-10-02',21,21,21,21,2)")
    conn.commit()
    conn.close()

    refreshed = simple_backtest.refresh_shared_price_history(["AAA"], db_path)
    assert refreshed is not first
    assert refreshed[refreshed.symbol == "AAA"].date.max().strftime("%Y-%m-%d") == "2026-10-02"
    assert refreshed[refreshed.symbol == "BBB"].date.max().strftime("%Y-%m-%d") == "2026-10-01"
    assert calls == 1
