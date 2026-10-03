import logging
import queue
import sqlite3
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from apps.desktop.dashboard import DesktopDashboard, _UIQueueLogHandler, _number


class _FakeTable:
    def __init__(self):
        self.rows = []

    def get_children(self):
        return tuple(range(len(self.rows)))

    def delete(self, *_items):
        self.rows.clear()

    def insert(self, _parent, _index, *, values):
        self.rows.append(values)


class _FakePagerWidget:
    def __init__(self, **options):
        self.options = options

    def configure(self, **options):
        self.options.update(options)


def _table_pager_app(row_count, page=0):
    app = SimpleNamespace(
        tables={"Market": _FakeTable()},
        table_rows={"Market": [{"symbol": f"SYM{i:03d}"} for i in range(row_count)]},
        table_pages={"Market": page},
        table_columns={"Market": ("symbol",)},
        table_pagers={"Market": (
            _FakePagerWidget(text="No rows"),
            _FakePagerWidget(state="disabled"),
            _FakePagerWidget(state="disabled"),
        )},
        status_vars={},
    )
    app._show_table_page = MethodType(DesktopDashboard._show_table_page, app)
    return app


def test_number_input_accepts_finite_values_and_rejects_invalid_values():
    assert _number("1,234.5") == 1234.5
    assert _number("", fallback=2.0) == 2.0
    for value in ("abc", "nan", "inf"):
        with pytest.raises(ValueError):
            _number(value)


def test_market_table_pagination_labels_every_row_on_all_pages():
    app = _table_pager_app(290)
    label, previous, next_page = app.table_pagers["Market"]
    expected_pages = (
        ("Rows 1 to 100 of 290", "SYM000", 100, "disabled", "normal"),
        ("Rows 101 to 200 of 290", "SYM100", 100, "normal", "normal"),
        ("Rows 201 to 290 of 290", "SYM200", 90, "normal", "disabled"),
    )

    for index, (text, first_symbol, visible_count, previous_state, next_state) in enumerate(expected_pages):
        DesktopDashboard._show_table_page(app, "Market")
        assert label.options["text"] == text
        assert app.tables["Market"].rows[0][0] == first_symbol
        assert len(app.tables["Market"].rows) == visible_count
        assert previous.options["state"] == previous_state
        assert next_page.options["state"] == next_state
        if index < len(expected_pages) - 1:
            DesktopDashboard._change_table_page(app, "Market", 1)


@pytest.mark.parametrize(
    ("row_count", "expected_label", "visible_count"),
    [(0, "No rows", 0), (100, "Rows 1 to 100 of 100", 100)],
)
def test_table_pager_handles_empty_and_exactly_one_page(row_count, expected_label, visible_count):
    app = _table_pager_app(row_count)
    DesktopDashboard._show_table_page(app, "Market")

    label, previous, next_page = app.table_pagers["Market"]
    assert label.options["text"] == expected_label
    assert len(app.tables["Market"].rows) == visible_count
    assert previous.options["state"] == "disabled"
    assert next_page.options["state"] == "disabled"


@pytest.mark.parametrize(("page", "bounded_page"), [(-4, 0), (99, 2)])
def test_table_pager_clamps_invalid_page_numbers(page, bounded_page):
    app = _table_pager_app(290, page=page)
    DesktopDashboard._show_table_page(app, "Market")

    assert app.table_pages["Market"] == bounded_page
    assert app.table_pagers["Market"][0].options["text"] == (
        "Rows 1 to 100 of 290" if bounded_page == 0 else "Rows 201 to 290 of 290"
    )


def test_table_pager_clamps_after_rows_shrink_and_refresh_resets_page():
    app = _table_pager_app(290, page=2)
    app.table_rows["Market"] = app.table_rows["Market"][:150]
    DesktopDashboard._show_table_page(app, "Market")
    label = app.table_pagers["Market"][0]

    assert app.table_pages["Market"] == 1
    assert label.options["text"] == "Rows 101 to 150 of 150"
    assert len(app.tables["Market"].rows) == 50

    DesktopDashboard._populate(app, "Market", app.table_rows["Market"][:75])
    assert app.table_pages["Market"] == 0
    assert label.options["text"] == "Rows 1 to 75 of 75"
    assert len(app.tables["Market"].rows) == 75


def test_log_entries_are_retained_while_collapsed_and_bounded():
    counts = []
    app = SimpleNamespace(
        log_entries=deque(maxlen=1000),
        log_panel_open=False,
        log_count=SimpleNamespace(set=counts.append),
    )

    for index in range(1001):
        DesktopDashboard._append_log_entry(app, logging.INFO, "Task", f"event {index}")

    assert len(app.log_entries) == 1000
    assert app.log_entries[0][3] == "event 1"
    assert app.log_entries[-1][3] == "event 1000"
    assert counts[-1] == "1,000 entries"
    assert app.log_entries[0][2] == "Task"


def test_log_panel_toggle_expands_and_collapses():
    class FakeWidget:
        def __init__(self):
            self.manager = ""
            self.text = ""

        def pack(self, **_kwargs):
            self.manager = "pack"

        def pack_forget(self):
            self.manager = ""

        def configure(self, *, text):
            self.text = text

    panel = FakeWidget()
    button = FakeWidget()
    renders = []
    app = SimpleNamespace(log_panel_open=False, log_panel=panel, logs_button=button)
    app._render_log_entries = MethodType(lambda self: renders.append(True), app)

    DesktopDashboard._toggle_log_panel(app)
    assert app.log_panel_open and panel.manager == "pack" and button.text == "Hide logs"
    DesktopDashboard._toggle_log_panel(app)
    assert not app.log_panel_open and panel.manager == "" and button.text == "Logs"
    assert renders == [True]


def test_log_severity_maps_to_stable_color_tags():
    assert DesktopDashboard._log_tag(logging.INFO) == "INFO"
    assert DesktopDashboard._log_tag(logging.WARNING) == "WARNING"
    assert DesktopDashboard._log_tag(logging.ERROR) == "ERROR"
    assert DesktopDashboard._log_tag(logging.CRITICAL) == "ERROR"


def test_visible_log_entry_includes_category_and_severity_tag():
    class FakeText:
        def __init__(self):
            self.inserted = []

        def configure(self, **_kwargs):
            pass

        def insert(self, _index, text, tag):
            self.inserted.append((text, tag))

        def see(self, _index):
            pass

    app = SimpleNamespace(
        log_entries=deque(maxlen=1000),
        log_panel_open=True,
        log_count=SimpleNamespace(set=lambda _value: None),
        log_text=FakeText(),
    )
    app._log_tag = DesktopDashboard._log_tag

    DesktopDashboard._append_log_entry(app, logging.ERROR, "History", "provider failed")

    text, tag = app.log_text.inserted[0]
    assert "[History] provider failed" in text
    assert tag == "ERROR"


def test_runtime_log_handler_can_queue_records_from_worker_threads():
    events = queue.SimpleQueue()
    handler = _UIQueueLogHandler(events)
    record = logging.LogRecord("backend.market", logging.WARNING, "market.py", 12, "provider timeout", (), None)
    worker = threading.Thread(target=handler.handle, args=(record,))
    worker.start()
    worker.join()

    assert events.get_nowait() == ("log", logging.WARNING, "backend.market", "provider timeout")


def test_ui_log_handler_restores_the_root_logger_level():
    root = logging.getLogger()
    original_level = root.level
    app = SimpleNamespace(
        _log_root=root,
        _previous_root_log_level=None,
        _ui_log_handler=None,
        ui_events=queue.SimpleQueue(),
    )
    try:
        root.setLevel(logging.WARNING)
        DesktopDashboard._install_ui_log_handler(app)
        assert root.level == logging.INFO
        DesktopDashboard._remove_ui_log_handler(app)
        assert root.level == logging.WARNING
    finally:
        if app._ui_log_handler:
            DesktopDashboard._remove_ui_log_handler(app)
        root.setLevel(original_level)


def test_background_task_queues_start_and_completion_entries():
    events = queue.SimpleQueue()
    app = SimpleNamespace(ui_events=events, jobs={}, executor=ThreadPoolExecutor(max_workers=1))
    app.heavy_executor = app.executor
    app._queue_log = MethodType(lambda self, level, category, message: events.put(("log", level, category, message)), app)
    completed = []
    key = "refresh:Market"
    try:
        DesktopDashboard._background(app, key, lambda: "loaded", completed.append)
        app.jobs[key].result(timeout=2)
        background_event = None
        queued_logs = []
        while True:
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "log":
                queued_logs.append(event[3])
            elif event[0] == "background":
                background_event = event

        assert any(message == f"Started {key}" for message in queued_logs)
        assert background_event is not None
        DesktopDashboard._finish_background(app, *background_event[1:])
        assert completed == ["loaded"]
        assert events.get_nowait() == ("log", logging.INFO, "Task", f"Completed {key}")
    finally:
        app.executor.shutdown(wait=True)


def test_history_subprocess_output_is_queued_with_category_and_severity(monkeypatch, tmp_path):
    lines = ["Connecting to history provider", "[1/2] AAA status=SUCCESS", "WARNING: partial response"]

    class FakeProcess:
        def __init__(self):
            self.stdout = iter(lines)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def wait(self):
            return 0

    monkeypatch.setattr("apps.desktop.dashboard.subprocess.Popen", lambda *_args, **_kwargs: FakeProcess())
    events = queue.SimpleQueue()
    app = SimpleNamespace(ui_events=events)
    cancel_file = tmp_path / "ingestion.cancel"

    result = DesktopDashboard._run_history_update(app, cancel_file, symbols=["AAA"])

    queued = []
    while True:
        try:
            queued.append(events.get_nowait())
        except queue.Empty:
            break
    history_logs = [event for event in queued if event[0] == "log"]
    assert result["output"] == lines
    assert [event[3] for event in history_logs] == lines
    assert all(event[2] == "History" for event in history_logs)
    assert history_logs[-1][1] == logging.WARNING


def test_market_coverage_reports_missing_months_and_benchmark_date(tmp_path: Path):
    db_path = tmp_path / "market.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE stock_prices (symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    conn.execute("CREATE TABLE market_quotes (symbol TEXT,fetched_at_utc TEXT)")
    conn.executemany(
        "INSERT INTO stock_prices (symbol,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        [
            ("AAA", "2026-04-15", 100, 100, 100, 100, 10),
            ("AAA", "2026-10-02", 110, 110, 110, 110, 10),
            ("NEPSE", "2026-04-15", 2700, 2700, 2700, 2700, 10),
        ],
    )
    conn.execute("INSERT INTO market_quotes VALUES ('AAA','2026-10-02T17:46:27+00:00')")
    conn.commit()
    conn.close()

    report = DesktopDashboard._market_coverage(db_path)

    assert "2026-04-15" in report
    assert "2026-10-02 · 1 symbols" in report
    assert "2026-05, 2026-06, 2026-07, 2026-08, 2026-09" in report


def test_all_stored_market_view_includes_old_symbols_and_blanks_stale_changes(tmp_path: Path):
    db_path = tmp_path / "market.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE stock_prices (symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    conn.executemany(
        "INSERT INTO stock_prices (symbol,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        [
            ("AAA", "2026-04-15", 100, 100, 100, 100, 10),
            ("AAA", "2026-10-01", 109, 109, 109, 110, 10),
            ("BBB", "2026-04-15", 50, 50, 50, 50, 10),
            ("NEPSE", "2026-04-15", 2700, 2700, 2700, 2700, 10),
            ("SECTOR::BANK", "2026-10-01", 100, 100, 100, 100, 10),
        ],
    )
    conn.commit()
    conn.close()

    rows = DesktopDashboard._load_all_stored_market(SimpleNamespace(_db_path=lambda: db_path))
    indexed = {row["symbol"]: row for row in rows}

    assert set(indexed) == {"AAA", "BBB"}
    assert indexed["AAA"]["date"] == "2026-10-01"
    assert indexed["AAA"]["chg"] is None
    assert indexed["BBB"]["date"] == "2026-04-15"


def test_rates_keep_available_sources_when_other_sources_fail(monkeypatch):
    from apps.tui.io import fetchers
    from backend.market import kalimati_market

    monkeypatch.setattr(kalimati_market, "init_kalimati_db", lambda: None)
    monkeypatch.setattr(kalimati_market, "refresh_kalimati", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(fetchers, "_fetch_gold_silver_prices", lambda: (_ for _ in ()).throw(RuntimeError("timeout")))
    monkeypatch.setattr(fetchers, "_fetch_noc_fuel_prices", lambda: {"petrol": 180, "date_bs": "today"})
    monkeypatch.setattr(fetchers, "_fetch_yahoo_futures_price", lambda *_args: None)
    monkeypatch.setattr(fetchers, "_fetch_nrb_forex_rates", lambda: [{"currency_code": "USD", "sell_rate": 135}])

    result = DesktopDashboard._load_rates(SimpleNamespace())

    assert [row["item"] for row in result["rows"]] == ["NOC Petrol", "NPR / USD"]
    assert "2 sources unavailable" in result["status"]
    assert "Kalimati: offline" in result["detail"]
    assert "Gold and silver: timeout" in result["detail"]


def test_rates_report_optional_source_failures_when_kalimati_succeeds(monkeypatch):
    from apps.tui.io import fetchers
    from backend.market import kalimati_market

    monkeypatch.setattr(kalimati_market, "init_kalimati_db", lambda: None)
    monkeypatch.setattr(kalimati_market, "refresh_kalimati", lambda: ([{"name_english": "Rice", "avg": 90}], "Kalimati updated"))
    monkeypatch.setattr(fetchers, "_fetch_gold_silver_prices", lambda: (_ for _ in ()).throw(RuntimeError("timeout")))
    monkeypatch.setattr(fetchers, "_fetch_noc_fuel_prices", lambda: {})
    monkeypatch.setattr(fetchers, "_fetch_yahoo_futures_price", lambda *_args: None)
    monkeypatch.setattr(fetchers, "_fetch_nrb_forex_rates", lambda: [])

    result = DesktopDashboard._load_rates(SimpleNamespace())

    assert result["status"] == "Kalimati updated · 1 market rates · 1 sources unavailable"
    assert "Gold and silver: timeout" in result["detail"]


def test_daily_scheduler_separates_recent_bars_from_manual_history_gaps(tmp_path):
    db_path = tmp_path / "market.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE market_quotes (symbol TEXT,fetched_at_utc TEXT)")
    conn.execute("CREATE TABLE stock_prices (symbol TEXT,date TEXT)")
    conn.executemany("INSERT INTO market_quotes VALUES (?, '2026-10-02T06:00:00+00:00')", [(s,) for s in ("AAA", "BBB", "CCC")])
    conn.executemany("INSERT INTO stock_prices VALUES (?,?)", [
        ("NEPSE", "2026-10-01"), ("AAA", "2026-10-01"),
        ("BBB", "2026-09-28"), ("CCC", "2026-09-01"),
    ])
    conn.commit()
    conn.close()

    due, old = DesktopDashboard._daily_history_symbols(SimpleNamespace(_db_path=lambda: db_path), "2026-10-02")

    assert due == ["AAA", "BBB", "NEPSE"]
    assert old == [("CCC", "2026-09-01")]

    missing = DesktopDashboard._record_scheduled_history_gaps(db_path, ["BBB"], "2026-10-02")
    due_after_attempt, _old_after_attempt = DesktopDashboard._daily_history_symbols(
        SimpleNamespace(_db_path=lambda: db_path), "2026-10-02"
    )
    assert missing == ["BBB"]
    assert "BBB" not in due_after_attempt
