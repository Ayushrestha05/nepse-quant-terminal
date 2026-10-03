"""Compact Tk desktop dashboard for NEPSE Quant."""

from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

PAGES = (
    "Market",
    "Portfolio",
    "Signals",
    "Lookup",
    "Agents",
    "Orders",
    "Watchlist",
    "Rates & Commodities",
    "Account",
    "Strategies",
    "Model Research",
    "Issues",
)


def _number(value: Any, fallback: float | None = None) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text:
        if fallback is not None:
            return fallback
        raise ValueError("Enter a number.")
    try:
        number = float(text)
    except ValueError:
        if fallback is not None:
            return fallback
        raise ValueError(f"Invalid number: {value!r}") from None
    if not math.isfinite(number):
        if fallback is not None:
            return fallback
        raise ValueError("Enter a finite number.")
    return number


def _rows(frame, limit: int = 0) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    view = frame.head(limit) if limit else frame
    return view.astype(object).where(view.notna(), None).to_dict(orient="records")


class _UIQueueLogHandler(logging.Handler):
    """Forward Python log records to the Tk thread through the UI event queue."""

    def __init__(self, events: queue.SimpleQueue):
        super().__init__(logging.INFO)
        self.events = events
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.events.put(("log", record.levelno, record.name or "Python", self.format(record)))
        except Exception:
            self.handleError(record)


class DesktopDashboard(tk.Tk):
    """Tk interface; expensive data loads and all simulations run in workers."""

    def __init__(self, *, smoke: bool = False):
        super().__init__()
        self.title("NEPSE Quant")
        self.geometry("1240x820")
        self.minsize(920, 620)
        self.smoke = smoke
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nepse-ui")
        self.heavy_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nepse-heavy")
        self.ui_events: queue.SimpleQueue = queue.SimpleQueue()
        self.log_entries: deque[tuple[str, int, str, str]] = deque(maxlen=1000)
        self.log_panel_open = False
        self._log_root = logging.getLogger()
        self._previous_root_log_level: int | None = None
        self._ui_log_handler: _UIQueueLogHandler | None = None
        self.jobs: dict[str, Any] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.tables: dict[str, ttk.Treeview] = {}
        self.table_columns: dict[str, tuple[str, ...]] = {}
        self.table_rows: dict[str, list[dict[str, Any]]] = {}
        self.table_pages: dict[str, int] = {}
        self.table_pagers: dict[str, tuple[ttk.Label, ttk.Button, ttk.Button]] = {}
        self.status_vars: dict[str, tk.StringVar] = {}
        self.detail_widgets: dict[str, tk.Text] = {}
        self.loaded: set[str] = set()
        self.current_page = "Market"
        self.current_account_id = "account_1"
        self.accounts: list[dict[str, Any]] = []
        self.engines: dict[str, Any] = {}
        self.engine_threads: list[threading.Thread] = []
        self.engine_threads_by_id: dict[str, threading.Thread] = {}
        self.research_cancel: threading.Event | None = None
        self.research_result: dict[str, Any] | None = None
        self.history_cancel_file: Path | None = None
        self.history_update_running = False
        self.history_errors: list[str] = []
        self._last_live_quote_refresh = 0.0
        self._scheduled_history_started = False
        self.strategy_payloads: dict[str, dict[str, Any]] = {}
        self.account_var = tk.StringVar(value="Loading accounts…")
        self.app_status = tk.StringVar(value="Ready")
        self._build_shell()
        self.app_status.trace_add("write", self._app_status_changed)
        if not smoke:
            self._init_runtime()
            self.after(50, self._poll_ui_events)
            self.after(50, self._load_current_page)
            self.after(60_000, self._auto_refresh)
            self.after(500, self._schedule_market_data)
        else:
            for name in PAGES:
                self.pages[name] = self._build_page(name)
        self._install_ui_log_handler()
        self.report_callback_exception = self._report_callback_exception
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_shell(self) -> None:
        style = ttk.Style(self)
        style.configure("TNotebook.Tab", padding=(11, 7))
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=("TkDefaultFont", 9, "bold"))
        style.configure("Navigation.Treeview", rowheight=31, borderwidth=0, relief="flat")
        style.configure("PageTitle.TLabel", font=("TkDefaultFont", 17, "bold"))
        style.configure("Brand.TLabel", font=("TkDefaultFont", 15, "bold"))
        self.theme_bg = style.lookup("TFrame", "background") or self.cget("background")
        self.theme_fg = style.lookup("TLabel", "foreground") or self.cget("foreground")

        header = ttk.Frame(self, padding=(16, 12, 16, 10))
        header.pack(fill="x")
        ttk.Label(header, text="NEPSE Quant", style="Brand.TLabel").pack(side="left")
        ttk.Label(header, text="Paper trading and research", padding=(12, 0)).pack(side="left")
        self.account_picker = ttk.Combobox(header, textvariable=self.account_var, width=25, state="readonly")
        self.account_picker.pack(side="right", padx=(6, 0))
        self.account_picker.bind("<<ComboboxSelected>>", self._account_changed)
        ttk.Button(header, text="Refresh", command=lambda: self._load_page(self.current_page, force=True)).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        nav = ttk.Frame(body, padding=(0, 4, 12, 0), width=205)
        content = ttk.Frame(body)
        body.add(nav, weight=0)
        body.add(content, weight=1)
        ttk.Label(nav, text="WORKSPACE", padding=(8, 2, 4, 9), font=("TkDefaultFont", 8, "bold")).pack(fill="x")
        self.page_list = ttk.Treeview(nav, show="tree", selectmode="browse", style="Navigation.Treeview", height=len(PAGES))
        self.page_list.column("#0", width=188, minwidth=150, stretch=True)
        for label in PAGES:
            self.page_list.insert("", "end", iid=label, text=label)
        self.page_list.pack(fill="both", expand=True)
        self.page_list.selection_set(PAGES[0])
        self.page_list.bind("<<TreeviewSelect>>", self._page_selected)
        self.content = content
        self.log_area = ttk.Frame(self)
        self.log_area.pack(fill="x", padx=12, pady=(0, 4))
        log_controls = ttk.Frame(self.log_area)
        log_controls.pack(fill="x")
        self.log_count = tk.StringVar(value="0 entries")
        ttk.Label(log_controls, textvariable=self.log_count, anchor="e").pack(side="right", padx=(8, 0))
        self.logs_button = ttk.Button(log_controls, text="Logs", command=self._toggle_log_panel)
        self.logs_button.pack(side="right")
        self.log_panel = ttk.Frame(self.log_area)
        log_text_frame = ttk.Frame(self.log_panel)
        log_text_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_text_frame, height=8, wrap="none", state="disabled")
        log_ybar = ttk.Scrollbar(log_text_frame, orient="vertical", command=self.log_text.yview)
        log_xbar = ttk.Scrollbar(log_text_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=log_ybar.set, xscrollcommand=log_xbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_ybar.grid(row=0, column=1, sticky="ns")
        log_xbar.grid(row=1, column=0, sticky="ew")
        log_text_frame.rowconfigure(0, weight=1)
        log_text_frame.columnconfigure(0, weight=1)
        self.log_text.tag_configure("INFO", foreground=self.theme_fg)
        self.log_text.tag_configure("WARNING", foreground="#a15c00")
        self.log_text.tag_configure("ERROR", foreground="#b42318")
        self.log_text.tag_configure("DEBUG", foreground="#667085")
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        ttk.Label(self, textvariable=self.app_status, anchor="w", padding=(10, 4)).pack(fill="x")

    def _install_ui_log_handler(self) -> None:
        self._previous_root_log_level = self._log_root.level
        self._ui_log_handler = _UIQueueLogHandler(self.ui_events)
        self._log_root.addHandler(self._ui_log_handler)
        if self._log_root.level > logging.INFO:
            self._log_root.setLevel(logging.INFO)

    def _remove_ui_log_handler(self) -> None:
        if self._ui_log_handler:
            self._log_root.removeHandler(self._ui_log_handler)
            self._ui_log_handler.close()
            self._ui_log_handler = None
            if self._previous_root_log_level is not None:
                self._log_root.setLevel(self._previous_root_log_level)

    def _queue_log(self, level: int, category: str, message: str) -> None:
        self.ui_events.put(("log", level, category, str(message)))

    def _app_status_changed(self, *_args) -> None:
        message = self.app_status.get().strip()
        if message:
            lowered = message.lower()
            level = logging.ERROR if any(word in lowered for word in ("failed", "error", "could not")) else logging.INFO
            self._queue_log(level, "Task", message)

    def _report_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)).rstrip()
        self._queue_log(logging.ERROR, "Task", detail)

    def _toggle_log_panel(self) -> None:
        self.log_panel_open = not self.log_panel_open
        if self.log_panel_open:
            self.log_panel.pack(fill="both", expand=False, pady=(4, 0))
            self._render_log_entries()
            self.logs_button.configure(text="Hide logs")
        else:
            self.log_panel.pack_forget()
            self.logs_button.configure(text="Logs")

    @staticmethod
    def _log_tag(level: int) -> str:
        if level >= logging.ERROR:
            return "ERROR"
        if level >= logging.WARNING:
            return "WARNING"
        if level < logging.INFO:
            return "DEBUG"
        return "INFO"

    def _append_log_entry(self, level: int, category: str, message: str) -> None:
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        clean_message = " ↵ ".join(str(message).splitlines())
        entry = (timestamp, level, str(category), clean_message)
        dropped_oldest = len(self.log_entries) == self.log_entries.maxlen
        self.log_entries.append(entry)
        self.log_count.set(f"{len(self.log_entries):,} entries")
        if not self.log_panel_open:
            return
        self.log_text.configure(state="normal")
        if dropped_oldest:
            self.log_text.delete("1.0", "2.0")
        tag = self._log_tag(level)
        line = f"{timestamp}  {logging.getLevelName(level):<8} [{category}] {clean_message}\n"
        self.log_text.insert("end", line, tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _render_log_entries(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        for timestamp, level, category, message in self.log_entries:
            line = f"{timestamp}  {logging.getLevelName(level):<8} [{category}] {message}\n"
            self.log_text.insert("end", line, self._log_tag(level))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _init_runtime(self) -> None:
        from apps.tui.io.persistence import (
            _account_dir,
            _bootstrap_paper_accounts,
            _load_profile_config,
        )

        self.accounts, self.current_account_id = _bootstrap_paper_accounts()
        profile = _load_profile_config()
        self.current_account_id = str(profile.get("current_account_id") or self.current_account_id)
        self.account_dirs = {str(row["id"]): _account_dir(str(row["id"])) for row in self.accounts}
        self._sync_agent_account_context()
        self._sync_account_picker()
        self._start_account_engines()

    def _sync_agent_account_context(self) -> None:
        account = self._account()
        os.environ["NEPSE_ACTIVE_ACCOUNT_ID"] = self.current_account_id
        os.environ["NEPSE_ACTIVE_ACCOUNT_NAME"] = str(account.get("name") or self.current_account_id)
        os.environ["NEPSE_ACTIVE_ACCOUNT_DIR"] = str(self.account_dirs[self.current_account_id])

    def _sync_account_picker(self) -> None:
        labels = [f"{row.get('name') or row['id']} ({row['id']})" for row in self.accounts]
        self.account_labels = dict(zip(labels, (str(row["id"]) for row in self.accounts)))
        self.account_picker.configure(values=labels)
        selected = next((label for label, account_id in self.account_labels.items() if account_id == self.current_account_id), "")
        self.account_var.set(selected)

    def _service(self, account_id: str | None = None):
        from backend.trading.paper_execution import PaperExecutionService

        account_id = account_id or self.current_account_id
        strategy_id = self._account(account_id).get("strategy_id", "")
        strategy = self._strategy(strategy_id)
        config = dict((strategy or {}).get("config") or {})
        return PaperExecutionService(
            account_id,
            account_dir=self.account_dirs[account_id],
            initial_capital=float(config.get("initial_capital") or 1_000_000),
            strategy_id=strategy_id,
            max_positions=int(config.get("max_positions") or 5),
            sector_limit=float(config.get("sector_limit") or 0.35),
        )

    def _account(self, account_id: str | None = None) -> dict[str, Any]:
        target = account_id or self.current_account_id
        return next((row for row in self.accounts if str(row.get("id")) == target), {"id": target, "name": target})

    def _strategy(self, strategy_id: str):
        from backend.trading import strategy_registry

        return strategy_registry.load_strategy(strategy_id) if strategy_id else None

    def _start_account_engines(self) -> None:
        """Retain the existing paper-only auto-trading loop for each account."""
        from apps.tui.io.persistence import _account_initial_capital_from_files
        from backend.trading import strategy_registry
        from backend.trading.tui_trading_engine import TUITradingEngine
        from configs.long_term import LONG_TERM_CONFIG

        for account in self.accounts:
            account_id = str(account.get("id") or "")
            if not account_id or account_id in self.engines:
                continue
            strategy_id = str(account.get("strategy_id") or "")
            strategy = strategy_registry.load_strategy(strategy_id) if strategy_id else None
            config = dict((strategy or {}).get("config") or {}) or dict(LONG_TERM_CONFIG)
            folder = self.account_dirs[account_id]
            capital = _account_initial_capital_from_files(folder, float(config.get("initial_capital") or 1_000_000))
            engine = TUITradingEngine(
                capital=capital,
                signal_types=list(config.get("signal_types") or LONG_TERM_CONFIG["signal_types"]),
                max_positions=int(config.get("max_positions") or 5),
                holding_days=int(config.get("holding_days") or 40),
                sector_limit=float(config.get("sector_limit") or 0.35),
                stop_loss_pct=float(config.get("stop_loss_pct") or 0.08),
                trailing_stop_pct=float(config.get("trailing_stop_pct") or 0.10),
                portfolio_file=folder / "paper_portfolio.csv",
                trade_log_file=folder / "paper_trade_log.csv",
                nav_log_file=folder / "paper_nav_log.csv",
                state_file=folder / "paper_state.json",
                account_id=account_id,
                strategy_id=strategy_id,
                strategy_config=config,
                on_status=lambda message, aid=account_id: self._engine_status(aid, message),
                on_portfolio_changed=lambda aid=account_id: self._engine_refresh(aid),
            )
            self.engines[account_id] = engine
            thread = threading.Thread(target=engine.run_loop, name=f"paper-{account_id}", daemon=True)
            thread.start()
            self.engine_threads.append(thread)
            self.engine_threads_by_id[account_id] = thread

    def _engine_status(self, account_id: str, message: str) -> None:
        if account_id == self.current_account_id:
            self.ui_events.put(("status", message))

    def _engine_refresh(self, account_id: str) -> None:
        if account_id == self.current_account_id and self.current_page in {"Portfolio", "Orders"}:
            self.ui_events.put(("refresh", self.current_page))

    def _poll_ui_events(self):
        while True:
            try:
                event = self.ui_events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "log":
                self._append_log_entry(event[1], event[2], event[3])
            elif event[0] == "status":
                self.app_status.set(event[1])
            elif event[0] == "refresh":
                self._load_page(event[1], force=True)
            elif event[0] == "background":
                _, key, done, payload, error = event
                self._finish_background(key, done, payload, error)
            elif event[0] == "research_progress":
                self._research_progress(event[1])
            elif event[0] == "history_progress":
                self._history_progress(event[1], event[2], event[3])
        self.after(100, self._poll_ui_events)

    def _page_selected(self, _event=None) -> None:
        selection = self.page_list.selection()
        if not selection:
            return
        self.current_page = str(selection[0])
        self._load_current_page()

    def _account_changed(self, _event=None) -> None:
        selected = self.account_labels.get(self.account_var.get())
        if not selected or selected == self.current_account_id:
            return
        self.current_account_id = selected
        self._sync_agent_account_context()
        from apps.tui.io.persistence import _load_profile_config, _save_profile_config

        profile = _load_profile_config()
        profile["current_account_id"] = selected
        _save_profile_config(profile)
        self.loaded.discard("Portfolio")
        self.loaded.discard("Orders")
        self.loaded.discard("Watchlist")
        self.loaded.discard("Account")
        self._load_page(self.current_page, force=True)

    def _load_current_page(self) -> None:
        if self.current_page not in self.pages:
            self.pages[self.current_page] = self._build_page(self.current_page)
        for page in self.pages.values():
            page.pack_forget()
        self.pages[self.current_page].pack(fill="both", expand=True)
        self._load_page(self.current_page)

    def _table(self, parent, name: str, columns: tuple[tuple[str, str, int], ...], height: int = 15):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        keys = tuple(row[0] for row in columns)
        table = ttk.Treeview(wrap, columns=keys, show="headings", height=height)
        self.table_columns[name] = keys
        for key, title, width in columns:
            table.heading(key, text=title)
            table.column(key, width=width, minwidth=50, stretch=True, anchor="w")
        ybar = ttk.Scrollbar(wrap, orient="vertical", command=table.yview)
        xbar = ttk.Scrollbar(wrap, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        pager = ttk.Frame(wrap)
        page_label = ttk.Label(pager, text="0 rows", anchor="center")
        previous = ttk.Button(pager, text="Previous", command=lambda: self._change_table_page(name, -1))
        next_page = ttk.Button(pager, text="Next", command=lambda: self._change_table_page(name, 1))
        previous.pack(side="left")
        page_label.pack(side="left", fill="x", expand=True, padx=8)
        next_page.pack(side="right")
        table.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        pager.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tables[name] = table
        self.table_rows[name] = []
        self.table_pages[name] = 0
        self.table_pagers[name] = (page_label, previous, next_page)
        return table

    def _change_table_page(self, name: str, offset: int) -> None:
        rows = self.table_rows.get(name, [])
        pages = max(1, (len(rows) + 99) // 100)
        self.table_pages[name] = min(max(self.table_pages.get(name, 0) + offset, 0), pages - 1)
        self._show_table_page(name)

    def _show_table_page(self, name: str) -> None:
        table = self.tables.get(name)
        if not table:
            return
        rows = self.table_rows.get(name, [])
        page = self.table_pages.get(name, 0)
        start, end = page * 100, min((page + 1) * 100, len(rows))
        table.delete(*table.get_children())
        keys = self.table_columns[name]
        for row in rows[start:end]:
            values = [row.get(key, "") for key in keys]
            table.insert("", "end", values=tuple("" if value is None else value for value in values))
        label, previous, next_page = self.table_pagers[name]
        label.configure(text=f"{start + 1:,}–{end:,} of {len(rows):,}" if rows else "No rows")
        previous.configure(state="normal" if page > 0 else "disabled")
        next_page.configure(state="normal" if end < len(rows) else "disabled")

    def _detail(self, parent, name: str, height: int = 7) -> tk.Text:
        widget = tk.Text(parent, height=height, wrap="word", undo=False)
        widget.pack(fill="both", expand=True, pady=(6, 0))
        widget.configure(background=self.theme_bg, foreground=self.theme_fg, insertbackground=self.theme_fg, borderwidth=0, relief="flat")
        widget.configure(state="disabled")
        self.detail_widgets[name] = widget
        return widget

    def _set_detail(self, name: str, content: str) -> None:
        widget = self.detail_widgets.get(name)
        if not widget:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _populate(self, name: str, rows: list[dict[str, Any]], *, status: str = "", detail: str = "") -> None:
        if name in self.tables:
            self.table_rows[name] = rows
            self.table_pages[name] = 0
            self._show_table_page(name)
        if name in self.status_vars:
            self.status_vars[name].set(status or f"{len(rows):,} rows")
        if detail:
            self._set_detail(name, detail)

    def _build_market(self, frame):
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 6))
        self.market_scope = tk.StringVar(value="Current session")
        ttk.Label(toolbar, text="View").pack(side="left", padx=(0, 4))
        self.market_scope_picker = ttk.Combobox(
            toolbar, textvariable=self.market_scope,
            values=("Current session", "All stored symbols"), width=21, state="readonly",
        )
        self.market_scope_picker.pack(side="left")
        self.market_scope_picker.bind("<<ComboboxSelected>>", lambda _event: self._load_page("Market", force=True))
        self.history_update_button = ttk.Button(toolbar, text="Update history", command=self._start_history_update)
        self.history_update_button.pack(side="left", padx=(10, 4))
        self.history_cancel_button = ttk.Button(toolbar, text="Cancel update", command=self._cancel_history_update, state="disabled")
        self.history_cancel_button.pack(side="left")
        self.history_error_button = ttk.Button(toolbar, text="Update errors", command=self._show_history_errors, state="disabled")
        self.history_error_button.pack(side="right")

        self.market_health = tk.StringVar(value="Checking local price and quote coverage…")
        ttk.Label(frame, textvariable=self.market_health, justify="left", anchor="w", wraplength=1000).pack(fill="x", pady=(0, 4))
        self.history_status = tk.StringVar(value="History updates run only when started.")
        ttk.Label(frame, textvariable=self.history_status, anchor="w").pack(fill="x")
        self.history_progress = ttk.Progressbar(frame, maximum=100, mode="determinate")
        self.history_progress.pack(fill="x", pady=(2, 7))
        self._table(frame, "Market", (("symbol", "Symbol", 100), ("date", "Last Date", 95), ("close", "Close", 90), ("chg", "Change %", 90), ("volume", "Volume", 100), ("turn", "Turnover", 115)), height=20)

    def _build_portfolio(self, frame):
        tabs = ttk.Notebook(frame)
        tabs.pack(fill="both", expand=True)
        holdings = ttk.Frame(tabs, padding=4)
        trades = ttk.Frame(tabs, padding=4)
        tabs.add(holdings, text="Holdings")
        tabs.add(trades, text="Trade history")
        self._table(holdings, "Portfolio", (("symbol", "Symbol", 100), ("shares", "Shares", 80), ("entry", "Entry", 90), ("last", "Last", 90), ("value", "Market Value", 130), ("pnl", "Unrealized P/L", 125), ("pnl_pct", "P/L %", 80)), height=18)
        self._table(trades, "Portfolio trades", (("date", "Date", 125), ("symbol", "Symbol", 90), ("action", "Action", 70), ("quantity", "Shares", 80), ("price", "Price", 95), ("pnl", "Net P/L", 100), ("reason", "Reason", 220)), height=18)

    def _build_signals(self, frame):
        self._table(frame, "Signals", (("symbol", "Symbol", 100), ("signal", "Signal", 150), ("strength", "Strength", 90), ("confidence", "Confidence", 95), ("score", "Score", 80), ("reason", "Reason", 420)), height=24)

    def _build_lookup(self, frame):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 6))
        self.lookup_symbol = tk.StringVar()
        ttk.Entry(row, textvariable=self.lookup_symbol, width=18).pack(side="left")
        ttk.Button(row, text="Lookup", command=self._lookup).pack(side="left", padx=5)
        self._table(frame, "Lookup", (("date", "Date", 100), ("open", "Open", 85), ("high", "High", 85), ("low", "Low", 85), ("close", "Close", 85), ("volume", "Volume", 110)), height=12)
        self._detail(frame, "Lookup", height=12)

    def _build_agents(self, frame):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Run analysis", command=self._run_agent).pack(side="left")
        ttk.Label(row, text="Analysis is informational; paper decisions stay algorithmic.", padding=(10, 0)).pack(side="left")
        self._table(frame, "Agents", (("symbol", "Symbol", 100), ("direction", "Direction", 100), ("verdict", "View", 110), ("confidence", "Confidence", 100), ("thesis", "Reason", 500)), height=15)
        self._detail(frame, "Agents", height=8)

    def _build_orders(self, frame):
        form = ttk.LabelFrame(frame, text="Paper order ticket", padding=6)
        form.pack(fill="x", pady=(0, 8))
        self.order_vars = {key: tk.StringVar(value=value) for key, value in {"side": "BUY", "symbol": "", "qty": "10", "price": "", "slippage": "2"}.items()}
        for label, key, width in (("Side", "side", 7), ("Symbol", "symbol", 12), ("Qty", "qty", 8), ("Limit", "price", 12), ("Slip %", "slippage", 8)):
            ttk.Label(form, text=label).pack(side="left", padx=(0, 3))
            if key == "side":
                ttk.Combobox(form, textvariable=self.order_vars[key], values=("BUY", "SELL"), width=width, state="readonly").pack(side="left", padx=(0, 9))
            else:
                ttk.Entry(form, textvariable=self.order_vars[key], width=width).pack(side="left", padx=(0, 9))
        ttk.Button(form, text="Submit", command=self._submit_order).pack(side="left", padx=(4, 8))
        ttk.Button(form, text="Cancel selected", command=self._cancel_order).pack(side="left")
        self._table(frame, "Orders", (("order_id", "Order", 110), ("action", "Side", 70), ("symbol", "Symbol", 90), ("quantity", "Qty", 70), ("limit_price", "Limit", 90), ("status", "Status", 90), ("created_at", "Created", 160)), height=21)

    def _build_watchlist(self, frame):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 6))
        self.watch_symbol = tk.StringVar()
        ttk.Entry(row, textvariable=self.watch_symbol, width=18).pack(side="left")
        ttk.Button(row, text="Add symbol", command=self._watch_add).pack(side="left", padx=5)
        ttk.Button(row, text="Remove selected", command=self._watch_remove).pack(side="left")
        self._table(frame, "Watchlist", (("symbol", "Symbol", 120), ("price", "Last", 100), ("change", "Change %", 100), ("note", "Note", 360)), height=23)

    def _build_rates_and_commodities(self, frame):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Fetch latest", command=lambda: self._load_page("Rates & Commodities", force=True)).pack(side="left")
        self._table(frame, "Rates & Commodities", (("item", "Market", 180), ("price", "Price", 120), ("change", "Change", 100), ("unit", "Unit", 100), ("date", "As of", 140)), height=24)
        self._detail(frame, "Rates & Commodities", height=3)

    def _build_account(self, frame):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 7))
        ttk.Button(row, text="New paper account", command=self._create_account).pack(side="left")
        ttk.Button(row, text="Import portfolio CSV", command=self._import_portfolio).pack(side="left", padx=5)
        self.nav_var = tk.StringVar()
        ttk.Label(row, text="Target NAV").pack(side="left", padx=(12, 4))
        ttk.Entry(row, textvariable=self.nav_var, width=14).pack(side="left")
        ttk.Button(row, text="Set NAV", command=self._set_nav).pack(side="left", padx=5)
        self._table(frame, "Account", (("id", "ID", 105), ("name", "Name", 160), ("strategy", "Strategy", 150), ("cash", "Cash", 120), ("nav", "NAV", 120), ("positions", "Positions", 90)), height=22)

    def _build_strategies(self, frame):
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Save editor as custom", command=self._save_strategy).pack(side="left")
        ttk.Button(bar, text="Assign to active account", command=self._assign_strategy).pack(side="left", padx=5)
        ttk.Label(bar, text="Backtest").pack(side="left", padx=(10, 3))
        today = date.today().isoformat()
        self.strategy_start = tk.StringVar(value=(date.today() - timedelta(days=365 * 5)).isoformat())
        self.strategy_end = tk.StringVar(value=today)
        ttk.Entry(bar, textvariable=self.strategy_start, width=12).pack(side="left")
        ttk.Entry(bar, textvariable=self.strategy_end, width=12).pack(side="left", padx=3)
        ttk.Button(bar, text="Run", command=self._run_strategy_backtest).pack(side="left")
        split = ttk.Panedwindow(frame, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split)
        right = ttk.Frame(split)
        split.add(left, weight=1)
        split.add(right, weight=2)
        self._table(left, "Strategies", (("id", "ID", 115), ("name", "Name", 180), ("source", "Source", 80), ("hold", "Hold", 60), ("signals", "Signals", 190)), height=22)
        self.tables["Strategies"].bind("<<TreeviewSelect>>", self._strategy_selected)
        self.strategy_editor = tk.Text(right, wrap="none", undo=True, background=self.theme_bg, foreground=self.theme_fg, insertbackground=self.theme_fg, borderwidth=0, relief="flat")
        self.strategy_editor.pack(fill="both", expand=True)
        self._detail(right, "Strategy result", height=6)

    def _build_model_research(self, frame):
        ttk.Label(frame, text="Research only — model scores never enter paper accounts.", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 5))
        form = ttk.Frame(frame)
        form.pack(fill="x", pady=(0, 6))
        self.research_vars = {
            "start": tk.StringVar(value=(date.today() - timedelta(days=365 * 8)).isoformat()),
            "end": tk.StringVar(value=date.today().isoformat()),
            "training": tk.StringVar(value="504"),
            "testing": tk.StringVar(value="63"),
            "slippage": tk.StringVar(value="0.5"),
            "capital": tk.StringVar(value="1000000"),
        }
        for label, key, width in (("Start", "start", 12), ("End", "end", 12), ("Train days", "training", 8), ("Test days", "testing", 8), ("Slippage %", "slippage", 8), ("Capital", "capital", 12)):
            ttk.Label(form, text=label).pack(side="left", padx=(0, 3))
            ttk.Entry(form, textvariable=self.research_vars[key], width=width).pack(side="left", padx=(0, 8))
        self.research_button = ttk.Button(form, text="Run comparison", command=self._run_research)
        self.research_button.pack(side="left", padx=(4, 3))
        self.research_cancel_button = ttk.Button(form, text="Cancel", command=self._cancel_research, state="disabled")
        self.research_cancel_button.pack(side="left")
        self.research_progress = ttk.Progressbar(frame, maximum=100, mode="determinate")
        self.research_progress.pack(fill="x", pady=(0, 5))
        self.research_metrics = tk.StringVar(value="Baseline   —\nModel      —\nNEPSE      —")
        ttk.Label(frame, textvariable=self.research_metrics, justify="left", anchor="w").pack(fill="x", pady=(0, 5))
        self.research_chart = tk.Canvas(frame, height=185, background=self.theme_bg, highlightthickness=1, highlightbackground=self.theme_fg)
        self.research_chart.pack(fill="x", pady=(0, 5))
        self.research_chart.bind("<Configure>", lambda _event: self._draw_research_chart())
        result_tabs = ttk.Notebook(frame)
        result_tabs.pack(fill="both", expand=True)
        periods = ttk.Frame(result_tabs, padding=4)
        trades = ttk.Frame(result_tabs, padding=4)
        result_tabs.add(periods, text="63-day periods")
        result_tabs.add(trades, text="Trade results")
        self._table(periods, "Research periods", (("test_start", "Start", 95), ("test_end", "End", 95), ("train_candidates", "Train N", 70), ("test_candidates", "Test N", 70), ("matured_test_outcomes", "Matured N", 80), ("candidate_hit_rate_pct", "Score hit %", 90), ("brier_score", "Brier", 75), ("baseline_return_pct", "Baseline %", 95), ("model_return_pct", "Model %", 95), ("baseline_trades", "Base trades", 80), ("model_trades", "Model trades", 80), ("baseline_win_rate_pct", "Base win %", 90), ("model_win_rate_pct", "Model win %", 90), ("baseline_profit_factor", "Base PF", 80), ("model_profit_factor", "Model PF", 85)), height=8)
        self._table(trades, "Research trades", (("portfolio", "Portfolio", 90), ("symbol", "Symbol", 80), ("signal_date", "Signal", 90), ("entry_date", "Entry", 90), ("entry_price", "Entry Price", 95), ("exit_date", "Exit", 90), ("exit_price", "Exit Price", 95), ("shares", "Shares", 70), ("net_pnl", "Net P/L", 100), ("net_return_pct", "Net %", 80), ("exit_reason", "Exit reason", 125)), height=8)

    def _build_issues(self, frame):
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Retry selected", command=self._retry_selected_issues).pack(side="left")
        ttk.Button(toolbar, text="Retry eligible", command=self._retry_eligible_issues).pack(side="left", padx=6)
        self.show_resolved_issues = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar, text="Show resolved", variable=self.show_resolved_issues,
            command=lambda: self._load_page("Issues", force=True),
        ).pack(side="left", padx=8)
        self.issues_progress = ttk.Progressbar(toolbar, mode="indeterminate", length=170)
        self.issues_progress.pack(side="right")
        self.issues_cancel_button = ttk.Button(toolbar, text="Cancel retry", command=self._cancel_history_update, state="disabled")
        self.issues_cancel_button.pack(side="right", padx=6)
        self._table(frame, "Issues", (
            ("issue_id", "ID", 48), ("source", "Source", 95), ("operation", "Operation", 95),
            ("symbol", "Symbol", 75), ("category", "Category", 115), ("status", "Status", 80),
            ("attempts", "Attempts", 70), ("last_attempt_utc", "Last attempt (UTC)", 150),
            ("retry_after_utc", "Retry after (UTC)", 150), ("detail", "Detail", 390),
        ), height=18)
        self.tables["Issues"].configure(selectmode="extended")

    def _build_page(self, name: str) -> tk.Frame:
        frame = ttk.Frame(self.content, padding=(14, 10, 12, 8))
        self.status_vars[name] = tk.StringVar(value="Select Refresh to load")
        heading = ttk.Frame(frame)
        heading.pack(fill="x", pady=(0, 9))
        ttk.Label(heading, text=name, style="PageTitle.TLabel").pack(anchor="w")
        build = getattr(self, f"_build_{name.lower().replace(' ', '_').replace('&', 'and')}", None)
        if build:
            build(frame)
        ttk.Label(frame, textvariable=self.status_vars[name], anchor="w").pack(fill="x", side="bottom", pady=(6, 0))
        return frame

    def _load_page(self, name: str, force: bool = False) -> None:
        if self.smoke or name in self.jobs or (name in self.loaded and not force):
            return
        loaders = {
            "Market": self._load_market,
            "Portfolio": self._load_portfolio,
            "Signals": self._load_signals,
            "Lookup": None,
            "Agents": self._load_agents,
            "Orders": self._load_orders,
            "Watchlist": self._load_watchlist,
            "Rates & Commodities": self._load_rates,
            "Account": self._load_accounts,
            "Strategies": self._load_strategies,
            "Model Research": None,
            "Issues": self._load_issues,
        }
        if name in {"Lookup", "Agents"} and not force:
            if name not in self.loaded:
                self.loaded.add(name)
                if name == "Agents":
                    self.status_vars[name].set("Ready · choose Run analysis when you need a fresh report.")
            return
        if name == "Model Research":
            self.loaded.add(name)
            self._background("research_restore", self._load_saved_research, self._restore_saved_research)
            return
        if name == "Lookup":
            self.loaded.add(name)
            return
        self.status_vars[name].set("Loading…")
        if name == "Rates & Commodities":
            self.status_vars[name].set("Fetching market rates…")
        account_id = self.current_account_id
        market_scope = self.market_scope.get() if name == "Market" else None
        if name in {"Portfolio", "Signals", "Orders", "Watchlist"}:
            loader = lambda: loaders[name](account_id)
        elif name == "Market":
            loader = lambda: self._load_market(market_scope)
        else:
            loader = loaders[name]
        heavy = name in {"Signals", "Agents", "Rates & Commodities", "Strategies"}
        self._background(f"load:{name}", loader, lambda payload: self._loaded_page(name, payload), heavy=heavy)
        self.jobs[name] = True

    def _loaded_page(self, name: str, payload: dict[str, Any]) -> None:
        self.jobs.pop(name, None)
        if payload.get("account_id") and payload["account_id"] != self.current_account_id:
            if name == self.current_page:
                self._load_page(name, force=True)
            return
        self.loaded.add(name)
        if name == "Market":
            self._populate(name, payload["rows"], status=payload["summary"])
            self.market_health.set(payload["health"])
        elif name == "Portfolio":
            self._populate(name, payload["rows"], status=payload["summary"])
            self._populate("Portfolio trades", payload["trades"], status=f"{len(payload['trades']):,} paper trades")
        elif name == "Signals":
            self._populate(name, payload["rows"], status=payload["status"])
        elif name == "Lookup":
            self._populate(name, payload["rows"], status=payload["status"], detail=payload["detail"])
        elif name == "Agents":
            self._populate(name, payload["rows"], status=payload["status"], detail=payload["detail"])
        elif name == "Rates & Commodities":
            self._populate(name, payload["rows"], status=payload["status"], detail=payload.get("detail", ""))
        elif name == "Issues":
            self._populate(name, payload["rows"], status=payload["status"])
        else:
            self._populate(name, payload["rows"], status=payload.get("status", ""))
        self.app_status.set(f"{name} updated")

    def _background(self, key: str, work: Callable[[], Any], done: Callable[[Any], None], *, heavy: bool = False) -> None:
        executor = self.heavy_executor if heavy else self.executor
        self._queue_log(logging.INFO, "Task", f"Started {key}")
        future = executor.submit(work)
        self.jobs[key] = future

        def finished(result):
            try:
                payload = result.result()
                error = None
            except Exception as exc:
                payload, error = None, exc
            self.ui_events.put(("background", key, done, payload, error))

        future.add_done_callback(finished)

    def _finish_background(self, key, done, payload, error):
        self.jobs.pop(key, None)
        if error:
            self._queue_log(logging.ERROR, "Task", f"{key} failed: {error}")
            target = key.split(":", 1)[-1]
            if target == "lookup":
                target = "Lookup"
            self.jobs.pop(target, None)
            if key == "portfolio_import":
                self._start_account_engines()
            if key == "research":
                self.research_cancel = None
                self.research_button.configure(state="normal")
                self.research_cancel_button.configure(state="disabled")
                self._set_research_status(f"Research failed: {error}")
                return
            if key == "history_update":
                self._history_update_failed(error)
                return
            if key == "issue_quote_retry":
                if hasattr(self, "issues_progress"):
                    self.issues_progress.stop()
                if "Issues" in self.status_vars:
                    self.status_vars["Issues"].set(f"Quote retry failed: {error}")
            if key == "research_restore":
                self._set_research_status(f"Could not load saved results: {error}")
                return
            if target in self.status_vars:
                self.status_vars[target].set(f"Error: {error}")
            self.app_status.set(f"{target}: {error}")
            return
        if done:
            done(payload)
        self._queue_log(logging.INFO, "Task", f"Completed {key}")

    def _auto_refresh(self):
        if not self.smoke and not self.research_cancel and not self.history_update_running and self.current_page not in {"Signals", "Agents", "Rates & Commodities", "Strategies", "Model Research"}:
            self.loaded.discard(self.current_page)
            self._load_page(self.current_page, force=True)
        self.after(60_000, self._auto_refresh)

    def _schedule_market_data(self):
        if self.smoke:
            return
        try:
            from backend.quant_pro.nepse_calendar import current_nepal_datetime, latest_completed_session, market_session_phase

            now = current_nepal_datetime()
            if (market_session_phase(now) == "OPEN" and not self.history_update_running
                    and time.monotonic() - self._last_live_quote_refresh >= 120):
                self._last_live_quote_refresh = time.monotonic()
                self._background("market_quotes", self._fetch_market_snapshot, self._market_quotes_finished, heavy=True)

            expected = latest_completed_session(now).isoformat()
            if not self.history_update_running and not self._scheduled_history_started:
                due, old = self._daily_history_symbols(expected)
                if old:
                    from backend.quant_pro.data_fetch_issues import record_issue

                    for symbol, last_date in old:
                        record_issue(
                            "merolagani", "history", "HISTORY_GAP",
                            f"Latest stored bar {last_date or 'missing'} is more than 14 days behind completed session {expected}; use Update history.",
                            symbol=symbol, attempts=0, db_path=self._db_path(),
                        )
                if due:
                    self._scheduled_history_started = True
                    self._start_history_update(due, scheduled=True, expected_session=expected)
        except Exception as exc:
            logging.getLogger(__name__).warning("Market-data scheduler check failed: %s", exc)
        self.after(15_000, self._schedule_market_data)

    @staticmethod
    def _fetch_market_snapshot():
        from backend.quant_pro.realtime_market import get_market_data_provider

        return get_market_data_provider().fetch_snapshot(force=True)

    @staticmethod
    def _retry_quote_issues(rows: list[dict[str, Any]]) -> str:
        from backend.quant_pro.realtime_market import get_market_data_provider

        provider = get_market_data_provider()
        summary = []
        for source in sorted({str(row.get("source") or "") for row in rows}):
            selected = [row for row in rows if row.get("source") == source]
            symbols = sorted({str(row.get("symbol") or "").strip().upper() for row in selected if row.get("symbol")})
            if source == "nepalstock":
                snapshot = provider.fetch_snapshot(force=True)
                summary.append(f"Nepalstock {len(snapshot.quotes):,} quotes")
            elif source == "merolagani" and symbols:
                prices = provider._fetch_merolagani_ltps(symbols)
                summary.append(f"MeroLagani {sum(price is not None for price in prices.values()):,}/{len(symbols):,} symbols")
        return ", ".join(summary) or "No supported quote issues selected"

    def _daily_history_symbols(self, expected_session: str) -> tuple[list[str], list[tuple[str, str | None]]]:
        from backend.quant_pro.data_fetch_issues import open_issue_symbols

        conn = sqlite3.connect(str(self._db_path()))
        try:
            latest_quote_ts = conn.execute("SELECT MAX(fetched_at_utc) FROM market_quotes").fetchone()[0]
            symbols = {str(row[0]).upper() for row in conn.execute(
                "SELECT DISTINCT symbol FROM market_quotes WHERE fetched_at_utc=?", (latest_quote_ts,)
            ) if row[0]} if latest_quote_ts else set()
            if not symbols:
                symbols = {str(row[0]).upper() for row in conn.execute(
                    "SELECT DISTINCT symbol FROM stock_prices WHERE symbol!='NEPSE' AND symbol NOT LIKE 'SECTOR::%'"
                ) if row[0]}
            symbols.add("NEPSE")
            last_dates = dict(conn.execute(
                "SELECT symbol,MAX(date) FROM stock_prices WHERE symbol IN (" + ",".join("?" for _ in symbols) + ") GROUP BY symbol",
                sorted(symbols),
            )) if symbols else {}
        finally:
            conn.close()
        unresolved = open_issue_symbols("history", db_path=self._db_path())
        expected = date.fromisoformat(expected_session)
        due, old = [], []
        for symbol in sorted(symbols):
            latest = last_dates.get(symbol)
            if symbol in unresolved or (latest and str(latest) >= expected_session):
                continue
            gap_days = (expected - date.fromisoformat(str(latest))).days if latest else 10_000
            if gap_days > 14:
                old.append((symbol, str(latest) if latest else None))
            else:
                due.append(symbol)
        return due, old

    def _market_quotes_finished(self, _snapshot=None):
        self.loaded.discard("Market")
        self.loaded.discard("Issues")
        if self.current_page == "Market":
            self._load_page("Market", force=True)
        if self.current_page == "Issues":
            self._load_page("Issues", force=True)

    @staticmethod
    def _record_scheduled_history_gaps(db_path: Path, symbols: list[str], expected_session: str) -> list[str]:
        from backend.quant_pro.data_fetch_issues import record_issue

        if not symbols:
            return []
        conn = sqlite3.connect(str(db_path))
        try:
            latest = dict(conn.execute(
                "SELECT symbol,MAX(date) FROM stock_prices WHERE symbol IN (" + ",".join("?" for _ in symbols) + ") GROUP BY symbol",
                sorted(set(symbols)),
            ))
        finally:
            conn.close()
        missing = [symbol for symbol in symbols if str(latest.get(symbol) or "") < expected_session]
        for symbol in missing:
            record_issue(
                "merolagani", "history", "HISTORY_GAP",
                f"No completed bar was stored for {expected_session}; use Retry selected or Update history.",
                symbol=symbol, db_path=db_path,
            )
        return missing

    @staticmethod
    def _market_coverage(db_path: Path) -> str:
        conn = sqlite3.connect(str(db_path))
        try:
            latest_price = conn.execute(
                "SELECT MAX(date) FROM stock_prices WHERE symbol!='NEPSE' AND symbol NOT LIKE 'SECTOR::%'"
            ).fetchone()[0]
            benchmark = conn.execute("SELECT MAX(date) FROM stock_prices WHERE symbol='NEPSE'").fetchone()[0]
            stored_count = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM stock_prices WHERE symbol!='NEPSE' AND symbol NOT LIKE 'SECTOR::%'"
            ).fetchone()[0]
            current_count = conn.execute(
                "SELECT COUNT(DISTINCT symbol) FROM stock_prices WHERE date=? AND symbol!='NEPSE' AND symbol NOT LIKE 'SECTOR::%'",
                (latest_price,),
            ).fetchone()[0] if latest_price else 0
            quote_ts, quote_count = conn.execute(
                "SELECT fetched_at_utc,COUNT(DISTINCT symbol) FROM market_quotes "
                "WHERE fetched_at_utc=(SELECT MAX(fetched_at_utc) FROM market_quotes)"
            ).fetchone()
            months = set()
            if latest_price:
                latest = date.fromisoformat(str(latest_price))
                latest_key = latest.year * 12 + latest.month - 1
                first_key = latest_key - 11
                first_month = f"{first_key // 12:04d}-{first_key % 12 + 1:02d}-01"
                months = {
                    row[0]
                    for row in conn.execute(
                        "SELECT DISTINCT substr(date,1,7) FROM stock_prices "
                        "WHERE date>=? AND symbol!='NEPSE' AND symbol NOT LIKE 'SECTOR::%'",
                        (first_month,),
                    )
                }
                first_date = conn.execute(
                    "SELECT MIN(date) FROM stock_prices WHERE symbol!='NEPSE' AND symbol NOT LIKE 'SECTOR::%'"
                ).fetchone()[0]
                first_key = max(first_key, date.fromisoformat(str(first_date)).year * 12 + date.fromisoformat(str(first_date)).month - 1)
                month_keys = [f"{key // 12:04d}-{key % 12 + 1:02d}" for key in range(first_key, latest_key + 1)]
                missing = [month for month in month_keys if month not in months and month != f"{latest.year:04d}-{latest.month:02d}"]
            else:
                missing = []
        finally:
            conn.close()

        quote_label = "no cached quotes"
        if quote_ts:
            try:
                local_ts = datetime.fromisoformat(str(quote_ts).replace("Z", "+00:00")).astimezone(
                    timezone(timedelta(hours=5, minutes=45))
                )
                quote_label = f"{quote_count} symbols at {local_ts:%Y-%m-%d %H:%M} NPT"
            except ValueError:
                quote_label = f"{quote_count} symbols at {quote_ts}"
        month_label = ", ".join(missing) if missing else "none in the last 12 months"
        return (
            f"Price bars: {latest_price or 'none'} · {current_count:,} symbols in that session · {stored_count:,} stored; "
            f"NEPSE index: {benchmark or 'none'}; quotes: {quote_label}.\n"
            f"Months without price bars in the recent history: {month_label}."
        )

    def _load_all_stored_market(self) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._db_path()))
        try:
            raw = conn.execute(
                """SELECT latest.symbol,latest.date,latest.close,latest.volume,
                          (SELECT prior.close FROM stock_prices prior
                           WHERE prior.symbol=latest.symbol AND prior.date<latest.date
                           ORDER BY prior.date DESC LIMIT 1),
                          (SELECT prior.date FROM stock_prices prior
                           WHERE prior.symbol=latest.symbol AND prior.date<latest.date
                           ORDER BY prior.date DESC LIMIT 1)
                   FROM stock_prices latest
                   JOIN (SELECT symbol,MAX(date) date FROM stock_prices
                         WHERE symbol!='NEPSE' AND symbol NOT LIKE 'SECTOR::%' GROUP BY symbol) most_recent
                     ON latest.symbol=most_recent.symbol AND latest.date=most_recent.date
                   ORDER BY latest.symbol"""
            ).fetchall()
        finally:
            conn.close()
        rows = []
        for symbol, last_date, close, volume, previous, previous_date in raw:
            change = None
            if previous and previous_date and (date.fromisoformat(str(last_date)) - date.fromisoformat(str(previous_date))).days <= 14:
                change = (float(close) - float(previous)) / float(previous) * 100 if float(previous) else None
            rows.append({
                "symbol": symbol, "date": last_date, "close": close, "chg": change,
                "volume": volume, "turn": float(close or 0) * float(volume or 0),
            })
        return rows

    def _load_market(self, scope: str = "Current session"):
        from backend.quant_pro.dashboard_data import MD

        market = MD(top_n=0)
        if scope == "All stored symbols":
            rows = self._load_all_stored_market()
            summary = f"{len(rows):,} symbols · latest stored price for each; unavailable changes are left blank"
        else:
            frame = market.df.copy()
            if frame.empty or not set(("symbol", "close", "chg", "volume", "turn")).issubset(frame.columns):
                rows = []
                summary = f"Market data unavailable · {market.err or 'No cached session'}"
            else:
                frame = frame.sort_values("chg", ascending=False, na_position="last")
                frame["date"] = market.latest
                rows = _rows(frame[["symbol", "date", "close", "chg", "volume", "turn"]])
                summary = (
                    f"Session {market.latest} · {len(rows):,} symbols · daily change available for {market.adv + market.dec + market.unch:,}; "
                    f"{len(rows) - market.adv - market.dec - market.unch:,} unavailable"
                )
        return {"rows": rows, "summary": summary, "health": self._market_coverage(self._db_path())}

    def _load_issues(self):
        from backend.quant_pro.data_fetch_issues import list_issues

        rows = list_issues(include_resolved=self.show_resolved_issues.get(), db_path=self._db_path())
        eligible = sum(
            not row.get("retry_after_utc")
            or row["retry_after_utc"] <= datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            for row in rows
        )
        return {"rows": rows, "status": f"{len(rows):,} open or degraded · {eligible:,} currently eligible for retry"}

    def _start_history_update(
        self, symbols: list[str] | None = None, *, scheduled: bool = False, retry_quotes: bool = False,
        deep_backfill: bool = False, quote_rows: list[dict[str, Any]] | None = None,
        expected_session: str | None = None,
    ) -> None:
        if self.history_update_running:
            return
        cancel_file = Path(tempfile.gettempdir()) / f"nepse-ingestion-{os.getpid()}-{uuid.uuid4().hex}.cancel"
        self.history_cancel_file = cancel_file
        self.history_update_running = True
        self.history_errors = []
        self.history_update_button.configure(state="disabled")
        self.history_cancel_button.configure(state="normal")
        if hasattr(self, "issues_cancel_button"):
            self.issues_cancel_button.configure(state="normal")
        self.history_error_button.configure(state="disabled")
        self.history_progress.configure(mode="indeterminate")
        self.history_progress.start(12)
        self.history_status.set(
            f"Updating {len(symbols):,} selected symbols…" if symbols is not None
            else "Starting the historical price update…"
        )
        if hasattr(self, "issues_progress"):
            self.issues_progress.start(12)
        self._background(
            "history_update",
            lambda: self._run_history_update(
                cancel_file, symbols=symbols, retry_quotes=retry_quotes,
                deep_backfill=(deep_backfill or (not scheduled and symbols is None)),
                quote_rows=quote_rows,
                expected_session=expected_session,
            ),
            self._history_update_finished,
            heavy=True,
        )

    def _run_history_update(
        self, cancel_file: Path, *, symbols: list[str] | None = None, retry_quotes: bool = False,
        deep_backfill: bool = False, quote_rows: list[dict[str, Any]] | None = None,
        expected_session: str | None = None,
    ) -> dict[str, Any]:
        script = Path(__file__).resolve().parents[2] / "scripts" / "ingestion" / "deterministic_daily_ingestion.py"
        symbols_file = cancel_file.with_suffix(".symbols")
        command = [sys.executable, "-u", str(script), "--source", "both", "--cancel-file", str(cancel_file)]
        if symbols is not None:
            symbols_file.write_text("\n".join(sorted(set(symbols))) + "\n", encoding="utf-8")
            command = [sys.executable, "-u", str(script), "--source", "file", "--symbols-file", str(symbols_file), "--cancel-file", str(cancel_file)]
        if deep_backfill:
            command.extend(("--backfill-days", "3650"))
        lines: list[str] = []
        run_id = None
        progress = re.compile(r"\[(\d+)/(\d+)\]")
        with subprocess.Popen(
            command,
            cwd=str(script.parents[2]),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as process:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                lines.append(line)
                if len(lines) > 30:
                    del lines[0]
                lowered = line.lower()
                level = (
                    logging.ERROR if any(word in lowered for word in ("error", "failed", "traceback"))
                    else logging.WARNING if "warning" in lowered
                    else logging.INFO
                )
                self.ui_events.put(("log", level, "History", line))
                started = re.search(r"started run_id=(\d+)", line)
                if started:
                    run_id = int(started.group(1))
                step = progress.search(line)
                if step:
                    self.ui_events.put(("history_progress", int(step.group(1)), int(step.group(2)), line))
            return_code = process.wait()

        status, succeeded, failed, fetched, latest = "FAILED", 0, 0, 0, "unknown"
        errors: list[str] = []
        if run_id is not None:
            conn = sqlite3.connect(str(self._db_path()))
            try:
                row = conn.execute(
                    "SELECT status,symbols_succeeded,symbols_failed,rows_fetched,latest_market_date_after "
                    "FROM ingestion_runs WHERE run_id=?", (run_id,),
                ).fetchone()
                if row:
                    status, succeeded, failed, fetched, latest = row
                errors = [f"{symbol}: {error or 'failed without a reason'}" for symbol, error in conn.execute(
                    "SELECT symbol,error FROM ingestion_run_symbols WHERE run_id=? AND status='FAILED' ORDER BY symbol",
                    (run_id,),
                )]
                successful_symbols = [str(row[0]) for row in conn.execute(
                    "SELECT symbol FROM ingestion_run_symbols WHERE run_id=? AND status='SUCCESS'", (run_id,)
                )]
            finally:
                conn.close()
            if successful_symbols:
                from backend.backtesting.simple_backtest import refresh_shared_price_history

                refresh_shared_price_history(successful_symbols, self._db_path())
            if expected_session:
                self._record_scheduled_history_gaps(self._db_path(), symbols or [], expected_session)
        else:
            successful_symbols = []
        quote_error = None
        quote_summary = ""
        cancelled = cancel_file.exists()
        if retry_quotes and not cancelled:
            try:
                quote_summary = self._retry_quote_issues(quote_rows or [])
            except Exception as exc:
                quote_error = str(exc)
        try:
            cancel_file.unlink(missing_ok=True)
            symbols_file.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "return_code": return_code, "status": status, "succeeded": succeeded,
            "failed": failed, "rows_fetched": fetched, "latest": latest,
            "errors": errors, "output": lines, "successful_symbols": successful_symbols,
            "quote_error": quote_error, "quote_summary": quote_summary,
        }

    def _history_progress(self, completed: int, total: int, line: str) -> None:
        self.history_progress.stop()
        self.history_progress.configure(mode="determinate", maximum=max(1, total), value=completed)
        self.history_status.set(f"{completed:,} of {total:,} symbols · {line}")

    def _finish_history_update_controls(self) -> None:
        self.history_update_running = False
        self.history_cancel_file = None
        self.history_progress.stop()
        self.history_progress.configure(mode="determinate", value=0)
        self.history_update_button.configure(state="normal")
        self.history_cancel_button.configure(state="disabled")
        if hasattr(self, "issues_cancel_button"):
            self.issues_cancel_button.configure(state="disabled")
        self._scheduled_history_started = False
        if hasattr(self, "issues_progress"):
            self.issues_progress.stop()

    def _history_update_finished(self, result: dict[str, Any]) -> None:
        self._finish_history_update_controls()
        self.history_errors = result["errors"]
        self.history_error_button.configure(state="normal" if self.history_errors else "disabled")
        status = result["status"]
        self.history_status.set(
            f"{status.title()} · {result['succeeded']:,} succeeded, {result['failed']:,} failed · "
            f"{result['rows_fetched']:,} rows · latest price date {result['latest']}"
        )
        if result["return_code"] and not result["errors"]:
            self.history_errors = result["output"]
            self.history_error_button.configure(state="normal")
        self.app_status.set(f"Price history update {status.lower()}")
        if result.get("quote_error"):
            self.app_status.set(f"Quote retry failed: {result['quote_error']}")
        elif result.get("quote_summary"):
            self.app_status.set(f"Quote retry completed · {result['quote_summary']}")
        self.loaded.discard("Issues")
        if self.current_page == "Issues":
            self._load_page("Issues", force=True)
        for page in ("Market", "Signals", "Portfolio", "Watchlist", "Account", "Lookup"):
            self.loaded.discard(page)
        if "Market" in self.pages:
            self._load_page("Market", force=True)
        if self.current_page in {"Signals", "Portfolio", "Watchlist", "Account"}:
            self._load_page(self.current_page, force=True)

    def _history_update_failed(self, error: Exception) -> None:
        self._finish_history_update_controls()
        from backend.quant_pro.data_fetch_issues import classify_fetch_error, record_issue, retry_after_from_error

        record_issue(
            "merolagani", "history", classify_fetch_error(error), str(error),
            retry_after_utc=retry_after_from_error(error),
        )
        self.history_status.set(f"History update failed: {error}")
        self.app_status.set(f"History update failed: {error}")

    def _cancel_history_update(self) -> None:
        if self.history_cancel_file:
            self.history_cancel_file.write_text("cancel", encoding="utf-8")
            self.history_cancel_button.configure(state="disabled")
            self.history_status.set("Cancellation requested · the current symbol will finish first.")
            self._queue_log(logging.WARNING, "History", "Cancellation requested; the current symbol will finish first.")

    def _show_history_errors(self) -> None:
        if "Issues" in self.page_list.get_children(""):
            self.page_list.selection_set("Issues")
            self.page_list.see("Issues")

    def _selected_issue_rows(self) -> list[dict[str, Any]]:
        table = self.tables.get("Issues")
        if table is None:
            return []
        by_id = {int(row["issue_id"]): row for row in self.table_rows.get("Issues", [])}
        selected = []
        for item in table.selection():
            values = table.item(item, "values")
            if values:
                try:
                    row = by_id.get(int(values[0]))
                except (ValueError, TypeError):
                    row = None
                if row:
                    selected.append(row)
        return selected

    def _retry_selected_issues(self) -> None:
        self._retry_issues(self._selected_issue_rows())

    def _retry_eligible_issues(self) -> None:
        from backend.quant_pro.data_fetch_issues import list_issues

        self._retry_issues(list_issues(eligible_only=True))

    def _retry_issues(self, rows: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = [row for row in rows if row.get("status") != "RESOLVED"]
        blocked = [row for row in rows if row.get("retry_after_utc") and row["retry_after_utc"] > now]
        if blocked:
            soonest = min(row["retry_after_utc"] for row in blocked)
            self.app_status.set(f"Retry paused by provider cooldown until {soonest}")
            return
        history = [row for row in rows if row.get("operation") == "history"]
        quotes = [row for row in rows if row.get("source") in {"nepalstock", "merolagani"} and row.get("operation") in {"quotes", "market_status"}]
        if history:
            symbols = sorted({str(row.get("symbol") or "").strip().upper() for row in history if row.get("symbol")})
            if not symbols:
                symbols = None
            self._start_history_update(
                symbols, retry_quotes=bool(quotes),
                deep_backfill=any(row.get("category") == "HISTORY_GAP" for row in history),
                quote_rows=quotes,
            )
        elif quotes:
            if hasattr(self, "issues_progress"):
                self.issues_progress.start(12)
            self.app_status.set("Retrying the latest market-wide quote snapshot…")
            self._background(
                "issue_quote_retry", lambda: self._retry_quote_issues(quotes),
                self._issue_quote_retry_finished, heavy=True,
            )
        elif rows:
            self.app_status.set("These issues need the source-specific update action on the Market page.")
        else:
            self.app_status.set("Select one or more eligible issues to retry.")

    def _issue_quote_retry_finished(self, summary="") -> None:
        if hasattr(self, "issues_progress"):
            self.issues_progress.stop()
        self.app_status.set(f"Quote retry completed · {summary}" if summary else "Quote retry completed")
        self._market_quotes_finished()

    def _load_portfolio(self, account_id: str):
        import pandas as pd

        service = self._service(account_id)
        state = service.get_account_execution_state()
        rows = []
        for position in state["positions"].values():
            last = float(position.last_ltp or position.entry_price)
            value = position.shares * last
            pnl = value - position.shares * position.entry_price - position.buy_fees
            rows.append({"symbol": position.symbol, "shares": position.shares, "entry": position.entry_price, "last": last, "value": value, "pnl": pnl, "pnl_pct": 100 * pnl / max(1, position.shares * position.entry_price)})
        trades = pd.read_csv(service.trade_log_file) if service.trade_log_file.exists() else pd.DataFrame()
        trade_rows = []
        for row in _rows(trades.iloc[::-1] if not trades.empty else trades):
            trade_rows.append({
                "date": row.get("Date", row.get("date")),
                "symbol": row.get("Symbol", row.get("symbol")),
                "action": row.get("Action", row.get("action")),
                "quantity": row.get("Shares", row.get("shares", row.get("quantity"))),
                "price": row.get("Price", row.get("price")),
                "pnl": row.get("PnL", row.get("pnl")),
                "reason": row.get("Reason", row.get("reason")),
            })
        summary = f"{self._account(account_id)['name']}  |  Cash NPR {state['cash']:,.0f}  |  NAV NPR {state['nav']:,.0f}  |  {len(rows)} positions"
        return {"rows": rows, "trades": trade_rows, "summary": summary, "account_id": account_id}

    def _load_signals(self, account_id: str):
        from backend.backtesting.simple_backtest import load_shared_price_history
        from backend.trading import strategy_registry
        from backend.trading.live_trader import generate_signals
        from configs.long_term import LONG_TERM_CONFIG

        strategy = strategy_registry.load_strategy(str(self._account(account_id).get("strategy_id") or ""))
        config = dict((strategy or {}).get("config") or LONG_TERM_CONFIG)
        prices = load_shared_price_history(self._db_path())
        signals, regime = generate_signals(prices, list(config.get("signal_types") or LONG_TERM_CONFIG["signal_types"]))
        rows = [{
            "symbol": row.get("symbol"),
            "signal": row.get("signal_type") or row.get("type"),
            "strength": row.get("strength"),
            "confidence": row.get("confidence"),
            "score": row.get("score") or (_number(row.get("strength")) * _number(row.get("confidence"))),
            "reason": row.get("reasoning") or row.get("reason", ""),
        } for row in signals]
        return {"rows": rows, "status": f"{len(rows)} signals · regime {regime} · paper ranking only", "account_id": account_id}

    def _load_agents(self):
        from backend.agents.agent_analyst import analyze

        result = analyze(force=True)
        stocks = result.get("stocks") or []
        rows = [{
            "symbol": row.get("symbol", ""),
            "direction": row.get("direction", ""),
            "verdict": row.get("verdict") or row.get("recommendation") or row.get("stance", ""),
            "confidence": row.get("confidence", ""),
            "thesis": row.get("thesis") or row.get("reasoning") or row.get("summary", ""),
        } for row in stocks]
        return {"rows": rows, "status": f"Analysis refreshed · {len(rows)} ideas", "detail": json.dumps(result.get("summary") or result.get("market_view") or {}, indent=2, default=str)}

    def _load_orders(self, account_id: str):
        state = self._service(account_id).get_account_execution_state()
        return {"rows": list(state["open_orders"]) + list(state["order_history"]), "status": f"{len(state['open_orders'])} open paper orders · no broker connection", "account_id": account_id}

    def _load_watchlist(self, account_id: str):
        path = self.account_dirs[account_id] / "watchlist.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = []
        symbols = [str(item.get("symbol") or item.get("label") or "").upper() if isinstance(item, dict) else str(item).upper() for item in raw]
        conn = sqlite3.connect(str(self._db_path()))
        rows = []
        try:
            for symbol in filter(None, symbols):
                quote = conn.execute("SELECT close, date FROM stock_prices WHERE symbol=? ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
                prev = conn.execute("SELECT close FROM stock_prices WHERE symbol=? ORDER BY date DESC LIMIT 1 OFFSET 1", (symbol,)).fetchone()
                price = float(quote[0]) if quote and quote[0] else 0.0
                old = float(prev[0]) if prev and prev[0] else price
                rows.append({"symbol": symbol, "price": price, "change": (price / old - 1) * 100 if old else 0, "note": quote[1] if quote else ""})
        finally:
            conn.close()
        return {"rows": rows, "status": f"{len(rows)} watched symbols", "account_id": account_id}

    def _load_rates(self):
        from apps.tui.io.fetchers import (
            _fetch_gold_silver_prices,
            _fetch_noc_fuel_prices,
            _fetch_nrb_forex_rates,
            _fetch_yahoo_futures_price,
        )
        from backend.market.kalimati_market import init_kalimati_db, refresh_kalimati

        rows, errors = [], []
        status = ""
        try:
            init_kalimati_db()
            commodities, status = refresh_kalimati()
            rows.extend({"item": row.get("name_english"), "price": row.get("avg"), "change": row.get("change_pct"), "unit": row.get("unit"), "date": row.get("date")} for row in commodities)
        except Exception as exc:
            errors.append(f"Kalimati: {exc}")
        try:
            metals = _fetch_gold_silver_prices() or {}
            for label in ("gold", "silver"):
                price = metals.get(f"{label}_per_tola")
                if price:
                    rows.append({"item": label.title(), "price": price, "change": "", "unit": "NPR/tola", "date": metals.get("date_bs", "")})
        except Exception as exc:
            errors.append(f"Gold and silver: {exc}")
        try:
            noc = _fetch_noc_fuel_prices() or {}
            for key, label in (("petrol", "Petrol"), ("diesel", "Diesel"), ("kerosene", "Kerosene"), ("lpg", "LPG")):
                if noc.get(key):
                    rows.append({"item": f"NOC {label}", "price": noc[key], "change": "", "unit": "NPR/litre" if key != "lpg" else "NPR/cylinder", "date": noc.get("date_bs", "")})
        except Exception as exc:
            errors.append(f"NOC fuel: {exc}")
        for symbol, label in (("CL=F", "Crude oil"), ("GC=F", "Gold futures")):
            try:
                record = _fetch_yahoo_futures_price(symbol, label)
                if record:
                    rows.append({"item": record.get("label") or record.get("name", "Global rate"), "price": record.get("value"), "change": record.get("change_pct", ""), "unit": record.get("unit", ""), "date": record.get("date", "")})
            except Exception as exc:
                errors.append(f"{label}: {exc}")
        try:
            for record in _fetch_nrb_forex_rates():
                rows.append({"item": f"NPR / {record.get('currency_code', '')}", "price": record.get("sell_rate") or record.get("buy_rate"), "change": record.get("change_pct", ""), "unit": record.get("currency_name", ""), "date": record.get("date", "")})
        except Exception as exc:
            errors.append(f"NRB forex: {exc}")
        summary = f"{len(rows)} market rates" + (f" · {len(errors)} sources unavailable" if errors else "")
        return {"rows": rows, "status": " · ".join(filter(None, (status, summary))), "detail": "\n".join(errors)}

    def _load_accounts(self):
        rows = []
        for account in self.accounts:
            service = self._service(str(account["id"]))
            state = service.get_account_execution_state()
            rows.append({"id": account["id"], "name": account.get("name", ""), "strategy": account.get("strategy_id", ""), "cash": f"{state['cash']:,.0f}", "nav": f"{state['nav']:,.0f}", "positions": len(state["positions"])})
        return {"rows": rows, "status": f"{len(rows)} paper accounts · active: {self.current_account_id}"}

    def _load_strategies(self):
        from backend.trading import strategy_registry
        from configs.long_term import LONG_TERM_CONFIG

        payloads = strategy_registry.list_strategies()
        if not payloads:
            payloads = [{"id": "default_c5", "name": "C5 Baseline", "source": "builtin", "config": dict(LONG_TERM_CONFIG)}]
        self.strategy_payloads = {str(row["id"]): row for row in payloads}
        return {"rows": [{"id": row["id"], "name": row.get("name"), "source": row.get("source"), "hold": (row.get("config") or {}).get("holding_days"), "signals": ", ".join((row.get("config") or {}).get("signal_types") or [])} for row in payloads], "status": f"{len(payloads)} strategies · select one to inspect or backtest"}

    @staticmethod
    def _load_saved_research():
        from backend.quant_pro.paths import get_data_dir

        target = get_data_dir(__file__) / "model_research" / "latest.json"
        return json.loads(target.read_text(encoding="utf-8")) if target.exists() else None

    def _restore_saved_research(self, payload):
        if payload:
            self.research_result = payload
            self._render_research(payload)
            self._set_research_status(f"Loaded saved results · {(payload.get('settings') or {}).get('out_of_sample_start_date', 'date unavailable')}")
        else:
            self._set_research_status("No saved comparison yet; choose a date range and run one.")

    @staticmethod
    def _db_path() -> Path:
        from backend.quant_pro.database import get_db_path

        return get_db_path()

    def _lookup(self):
        symbol = self.lookup_symbol.get().strip().upper()
        if not symbol or "lookup" in self.jobs:
            return
        self.status_vars["Lookup"].set(f"Loading {symbol}…")
        def work():
            from backend.quant_pro.dashboard_data import MD
            from backend.quant_pro.stock_report import build_stock_report

            detail = MD(top_n=0).detail(symbol, limit=None)
            if not detail:
                raise ValueError(f"No market history found for {symbol}")
            history = _rows(detail["h"])
            report = build_stock_report(symbol, float(detail["lat"]["close"]))
            snapshot = "\n".join(f"{label}: {value}" for label, value in report.get("snapshot", []))
            risks = "\n".join(f"• {item}" for item in report.get("risks", []))
            summary = "\n".join(filter(None, (
                report.get("company_name", ""),
                f"View: {report.get('signal', '—')} · score {report.get('score', '—')}",
                report.get("summary", ""),
                "\nFinancial snapshot\n" + snapshot if snapshot else "",
                "\nRisks to monitor\n" + risks if risks else "",
            )))
            return {"rows": history, "status": f"{symbol} · latest close {float(detail['lat']['close']):,.2f} · {detail['chg']:+.2f}%", "detail": summary}
        self._background("lookup", work, lambda result: self._loaded_page("Lookup", result))

    def _run_agent(self):
        self.loaded.discard("Agents")
        self._load_page("Agents", force=True)

    def _submit_order(self):
        try:
            side = self.order_vars["side"].get().upper()
            symbol = self.order_vars["symbol"].get().strip().upper()
            quantity = int(self.order_vars["qty"].get())
            price_text = self.order_vars["price"].get().strip()
            slippage_text = self.order_vars["slippage"].get().strip()
            limit_price = _number(price_text) if price_text else 0.0
            slippage = _number(slippage_text) if slippage_text else 2.0
            if not symbol or quantity < 1 or limit_price < 0 or not 0 <= slippage <= 5:
                raise ValueError("Enter a symbol, positive quantity, non-negative limit, and 0–5% slippage.")
        except ValueError as exc:
            messagebox.showerror("Invalid paper order", str(exc), parent=self)
            return
        account_id = self.current_account_id
        self.app_status.set("Submitting paper order…")
        def work():
            price = limit_price
            if price == 0:
                conn = sqlite3.connect(str(self._db_path()))
                try:
                    quote = conn.execute("SELECT close FROM stock_prices WHERE symbol=? ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
                finally:
                    conn.close()
                price = float(quote[0]) if quote and quote[0] else 0.0
                if price <= 0:
                    raise ValueError(f"No saved market price for {symbol}; enter a limit price.")
            result = self._service(account_id).submit_order(account_id, side, symbol, quantity, price, "desktop_manual", "manual order", slippage_pct=slippage)
            return result.message
        self._background("order_submit", work, lambda message: (self.app_status.set(message), self._load_page("Orders", force=True)))

    def _cancel_order(self):
        table = self.tables.get("Orders")
        selection = table.selection() if table else ()
        if not selection:
            return
        order_id = table.item(selection[0], "values")[0]
        account_id = self.current_account_id
        self._background("order_cancel", lambda: self._service(account_id).cancel_order(account_id, order_id, "cancelled from desktop").message, lambda message: (self.app_status.set(message), self._load_page("Orders", force=True)))

    def _watchlist_path(self) -> Path:
        return self.account_dirs[self.current_account_id] / "watchlist.json"

    def _watchlist_values(self) -> list[dict[str, str]]:
        try:
            raw = json.loads(self._watchlist_path().read_text(encoding="utf-8"))
        except Exception:
            raw = []
        values = []
        for item in raw:
            symbol = (item.get("symbol") or item.get("label")) if isinstance(item, dict) else item
            symbol = str(symbol or "").strip().upper()
            if symbol and not any(row["symbol"] == symbol for row in values):
                values.append({"kind": "stock", "key": f"stock:{symbol}", "label": symbol, "symbol": symbol})
        return values

    def _save_watchlist(self, values):
        self._watchlist_path().write_text(json.dumps(values, indent=2), encoding="utf-8")

    def _watch_add(self):
        symbol = self.watch_symbol.get().strip().upper()
        if symbol:
            self._queue_log(logging.INFO, "Task", f"Adding {symbol} to the watchlist")
            values = self._watchlist_values()
            if not any(row["symbol"] == symbol for row in values):
                values.append({"kind": "stock", "key": f"stock:{symbol}", "label": symbol, "symbol": symbol})
                self._save_watchlist(values)
                self._queue_log(logging.INFO, "Task", f"Added {symbol} to the watchlist")
            else:
                self._queue_log(logging.INFO, "Task", f"{symbol} is already on the watchlist")
            self.watch_symbol.set("")
            self.loaded.discard("Watchlist")
            self._load_page("Watchlist", force=True)

    def _watch_remove(self):
        table = self.tables["Watchlist"]
        selected = table.selection()
        if selected:
            symbol = table.item(selected[0], "values")[0]
            self._queue_log(logging.INFO, "Task", f"Removing {symbol} from the watchlist")
            self._save_watchlist([row for row in self._watchlist_values() if row["symbol"] != symbol])
            self._queue_log(logging.INFO, "Task", f"Removed {symbol} from the watchlist")
            self.loaded.discard("Watchlist")
            self._load_page("Watchlist", force=True)

    def _create_account(self):
        from datetime import datetime
        from apps.tui.io.persistence import _account_dir, _blank_account_files, _load_accounts_registry, _save_accounts_registry
        from backend.trading import strategy_registry

        name = simpledialog.askstring("New paper account", "Account name", parent=self)
        if not name or not name.strip():
            return
        self._queue_log(logging.INFO, "Task", f"Creating paper account {name.strip()}")
        registry = _load_accounts_registry()
        account_id = f"account_{max([int(str(row.get('id', 'account_0')).split('_')[-1]) for row in registry.get('accounts', []) if str(row.get('id', '')).split('_')[-1].isdigit()] + [0]) + 1}"
        account_dir = _account_dir(account_id)
        _blank_account_files(account_dir)
        now = datetime.now().isoformat(timespec="seconds")
        account = {"id": account_id, "name": name.strip(), "strategy_id": strategy_registry.default_strategy_for_account(account_id), "created_at": now, "updated_at": now}
        registry["accounts"] = list(registry.get("accounts") or []) + [account]
        _save_accounts_registry(registry)
        self.accounts.append(account)
        self.account_dirs[account_id] = account_dir
        self._start_account_engines()
        self._sync_account_picker()
        self.account_var.set(next(label for label, aid in self.account_labels.items() if aid == account_id))
        self._account_changed()
        self.loaded.discard("Account")
        self._load_page("Account", force=True)
        self._queue_log(logging.INFO, "Task", f"Created paper account {account_id}")

    def _set_nav(self):
        self._queue_log(logging.INFO, "Task", "Updating paper account NAV")
        try:
            target = _number(self.nav_var.get())
            if target <= 0:
                raise ValueError("Target NAV must be positive.")
            service = self._service()
            state = service._load_state()
            positions = service.get_account_execution_state()["positions"]
            marked = sum(position.shares * float(position.last_ltp or position.entry_price) for position in positions.values())
            if not math.isfinite(marked):
                raise ValueError("Current holdings contain an invalid market value.")
            cash = target - marked
            if cash < 0:
                raise ValueError("Target NAV cannot be below the current marked holdings value.")
            state.update(cash=cash, daily_start_nav=target, initial_capital=target)
            service._save_state(state)
            engine = self.engines.get(self.current_account_id)
            if engine:
                engine._sync_from_execution_service()
                engine._daily_start_nav = target
            self.loaded.discard("Account")
            self.loaded.discard("Portfolio")
            self._load_page(self.current_page, force=True)
            self._queue_log(logging.INFO, "Task", "Paper account NAV updated")
        except Exception as exc:
            self._queue_log(logging.ERROR, "Task", f"Paper account NAV update failed: {exc}")
            messagebox.showerror("Unable to set NAV", str(exc), parent=self)

    def _import_portfolio(self):
        path = filedialog.askopenfilename(parent=self, title="Import portfolio", filetypes=(("CSV", "*.csv"), ("All files", "*.*")))
        if not path:
            return
        account_id = self.current_account_id
        engine = self.engines.get(account_id)
        if engine:
            engine.stop()
            self.engines.pop(account_id, None)
        def work():
            thread = self.engine_threads_by_id.get(account_id)
            if thread:
                thread.join()
            import pandas as pd
            from apps.tui.io.csv_import import _normalize_import_portfolio

            portfolio = _normalize_import_portfolio(pd.read_csv(path))
            service = self._service(account_id)
            state = service._load_state()
            mark = sum(float(row.get("Quantity") or 0) * float(row.get("Last_LTP") or row.get("Buy_Price") or 0) for row in portfolio.to_dict("records"))
            if not math.isfinite(mark):
                raise ValueError("Imported holdings contain an invalid market value.")
            capital = float(state.get("initial_capital") or state.get("daily_start_nav") or 1_000_000)
            if mark > capital:
                raise ValueError(f"Imported holdings are worth NPR {mark:,.0f}, above account capital NPR {capital:,.0f}.")
            target = self.account_dirs[account_id] / "paper_portfolio.csv"
            portfolio.to_csv(target, index=False)
            state["cash"] = capital - mark
            service._save_state(state)
            return f"Imported {len(portfolio)} holding(s) into {account_id}."
        def imported(message):
            self.app_status.set(message)
            self._start_account_engines()
            self._load_page("Portfolio", force=True)
        self._background("portfolio_import", work, imported)

    def _strategy_selected(self, _event=None):
        selected = self.tables["Strategies"].selection()
        if not selected:
            return
        strategy_id = str(self.tables["Strategies"].item(selected[0], "values")[0])
        payload = self.strategy_payloads.get(strategy_id, {})
        self.strategy_editor.delete("1.0", "end")
        self.strategy_editor.insert("1.0", json.dumps(payload, indent=2, default=str))

    def _save_strategy(self):
        self._queue_log(logging.INFO, "Task", "Saving custom strategy")
        try:
            from backend.trading import strategy_registry

            payload = json.loads(self.strategy_editor.get("1.0", "end"))
            saved = strategy_registry.save_custom_strategy(payload)
            self.loaded.discard("Strategies")
            self._load_page("Strategies", force=True)
            self.app_status.set(f"Saved custom strategy {saved['name']} ({saved['id']})")
        except Exception as exc:
            self._queue_log(logging.ERROR, "Task", f"Saving custom strategy failed: {exc}")
            messagebox.showerror("Invalid strategy", str(exc), parent=self)

    def _assign_strategy(self):
        selected = self.tables["Strategies"].selection()
        if not selected:
            messagebox.showinfo("Strategies", "Select a strategy first.", parent=self)
            return
        strategy_id = str(self.tables["Strategies"].item(selected[0], "values")[0])
        self._queue_log(logging.INFO, "Task", f"Assigning strategy {strategy_id} to {self.current_account_id}")
        from apps.tui.io.persistence import _load_accounts_registry, _save_accounts_registry
        from configs.long_term import LONG_TERM_CONFIG

        registry = _load_accounts_registry()
        for account in registry.get("accounts", []):
            if str(account.get("id")) == self.current_account_id:
                account["strategy_id"] = strategy_id
        _save_accounts_registry(registry)
        self.accounts = list(registry.get("accounts") or [])
        engine = self.engines.get(self.current_account_id)
        if engine:
            config = dict((self._strategy(strategy_id) or {}).get("config") or LONG_TERM_CONFIG)
            engine.strategy_id = strategy_id
            engine.strategy_config = config
            engine.signal_types = list(config.get("signal_types") or [])
            engine.max_positions = int(config.get("max_positions") or 5)
            engine.holding_days = int(config.get("holding_days") or 40)
            engine.sector_limit = float(config.get("sector_limit") or 0.35)
            engine.stop_loss_pct = float(config.get("stop_loss_pct") or 0.08)
            engine.trailing_stop_pct = float(config.get("trailing_stop_pct") or 0.10)
            engine._paper_execution = self._service(self.current_account_id)
            engine._sync_from_execution_service()
        self.app_status.set(f"Assigned {strategy_id} to {self.current_account_id}; paper engine updated.")
        self.loaded.discard("Account")

    def _run_strategy_backtest(self):
        selected = self.tables["Strategies"].selection()
        if not selected:
            return
        strategy_id = str(self.tables["Strategies"].item(selected[0], "values")[0])
        start, end = self.strategy_start.get().strip(), self.strategy_end.get().strip()
        if not start or not end:
            messagebox.showerror("Backtest", "Enter start and end dates.", parent=self)
            return
        self._background("strategy_backtest", lambda: self._strategy_backtest(strategy_id, start, end), lambda result: self._set_detail("Strategy result", json.dumps(result, indent=2, default=str)), heavy=True)

    @staticmethod
    def _strategy_backtest(strategy_id, start, end):
        from backend.trading import strategy_registry
        from configs.long_term import LONG_TERM_CONFIG

        strategy = strategy_registry.load_strategy(strategy_id) or {"id": strategy_id, "name": strategy_id, "config": LONG_TERM_CONFIG}
        return strategy_registry.run_strategy_backtest(strategy, start_date=start, end_date=end, capital=float((strategy.get("config") or {}).get("initial_capital") or 1_000_000))

    def _run_research(self):
        if self.research_cancel:
            return
        try:
            start = date.fromisoformat(self.research_vars["start"].get().strip()).isoformat()
            end = date.fromisoformat(self.research_vars["end"].get().strip()).isoformat()
            training_days = int(self.research_vars["training"].get())
            test_days = int(self.research_vars["testing"].get())
            slippage_pct = _number(self.research_vars["slippage"].get()) / 100
            capital = _number(self.research_vars["capital"].get())
            if start >= end or training_days < 60 or test_days < 1 or not 0 <= slippage_pct <= 0.05 or capital <= 0:
                raise ValueError("Use ordered ISO dates, at least 60 training days, positive test days and capital, and 0–5% slippage.")
        except ValueError as exc:
            messagebox.showerror("Research settings", str(exc), parent=self)
            return
        from backend.trading import strategy_registry
        from configs.long_term import LONG_TERM_CONFIG

        strategy_id = str(self._account().get("strategy_id") or "default_c5")
        strategy = strategy_registry.load_strategy(strategy_id) or {"config": LONG_TERM_CONFIG}
        config = dict(strategy.get("config") or LONG_TERM_CONFIG)
        config["initial_capital"] = capital
        self.research_cancel = threading.Event()
        self.research_button.configure(state="disabled")
        self.research_cancel_button.configure(state="normal")
        self.research_progress.configure(value=0)
        self._set_research_status("Research running in background…")
        def work():
            from backend.quant_pro.model_research import run_model_research

            result = run_model_research(
                start,
                end,
                config,
                training_days=training_days,
                test_days=test_days,
                slippage_pct=slippage_pct,
                cancel_event=self.research_cancel,
                progress_callback=lambda item: self.ui_events.put(("research_progress", dict(item))),
            )
            payload = result.to_dict()
            from backend.quant_pro.paths import ensure_dir, get_data_dir

            target = ensure_dir(get_data_dir(__file__) / "model_research") / "latest.json"
            payload["saved_to"] = str(target)
            target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            return payload
        self._background("research", work, self._research_complete, heavy=True)

    def _research_progress(self, payload):
        if "progress_pct" in payload:
            self.research_progress.configure(value=payload["progress_pct"])
        message = payload.get("message") or payload.get("phase") or payload.get("stage") or "Running…"
        self._queue_log(logging.INFO, "Research", str(message))
        self._set_research_status(message)

    def _research_complete(self, payload):
        self.research_cancel = None
        self.research_button.configure(state="normal")
        self.research_cancel_button.configure(state="disabled")
        self.research_result = payload
        self._render_research(payload)
        self._set_research_status(f"Complete · results saved to {payload.get('saved_to', '')}")

    def _cancel_research(self):
        if self.research_cancel:
            self.research_cancel.set()
            self._set_research_status("Cancellation requested…")

    def _set_research_status(self, message):
        if "Model Research" in self.status_vars:
            self.status_vars["Model Research"].set(str(message))
        self.app_status.set(str(message))

    def _render_research(self, payload):
        def metric(row):
            pf = row.get("profit_factor")
            return (f"net {row.get('total_pnl', 0):,.0f} NPR · return {row.get('total_return_pct', 0):+.2f}% · win {row.get('win_rate_pct', 0):.1f}% · PF {'∞' if pf is None else f'{pf:.2f}'} · drawdown {row.get('max_drawdown_pct', 0):.2f}% · {row.get('trade_count', 0)} trades")
        self.research_metrics.set(
            "Out of sample from " + payload["settings"]["out_of_sample_start_date"] + "\n"
            + f"Fixed-horizon labels · slippage {payload['settings']['slippage_pct'] * 100:.2f}% · "
            + f"rolling {payload['settings']['training_days']} / {payload['settings']['test_days']} trading days\n"
            + "Baseline  " + metric(payload["baseline"]) + "\n"
            + "Model     " + metric(payload["model"])
        )
        self._draw_research_chart(payload)
        self._populate("Research periods", payload.get("folds") or [], status=f"{len(payload.get('folds') or [])} non-overlapping test windows")
        trades = [{"portfolio": portfolio, **trade} for portfolio in ("Baseline", "Model") for trade in payload.get(f"{portfolio.lower()}_trades", [])]
        trades.sort(key=lambda row: row.get("signal_date", ""), reverse=True)
        self._populate("Research trades", trades, status=f"{len(trades):,} trades · saved in latest.json")

    def _draw_research_chart(self, payload=None):
        payload = payload or self.research_result
        canvas = getattr(self, "research_chart", None)
        if not payload or not canvas:
            return
        canvas.delete("all")
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        pad = 36
        series = (("Baseline", payload.get("baseline_curve", []), "#1769aa"), ("Model", payload.get("model_curve", []), "#188038"), ("NEPSE", payload.get("nepse_curve", []), "#999999"))
        values = [float(point[1]) for _, curve, _ in series for point in curve if len(point) > 1]
        if not values:
            return
        low, high = min(values), max(values)
        if high <= low:
            high = low + 0.01
        canvas.create_line(pad, height - pad, width - 10, height - pad, fill=self.theme_fg)
        canvas.create_line(pad, pad, pad, height - pad, fill=self.theme_fg)
        for index, (label, curve, color) in enumerate(series):
            if len(curve) < 2:
                continue
            coords = []
            for i, point in enumerate(curve):
                x = pad + i * (width - pad - 14) / max(1, len(curve) - 1)
                y = height - pad - (float(point[1]) - low) * (height - 2 * pad) / (high - low)
                coords.extend((x, y))
            canvas.create_line(*coords, fill=color, width=2, smooth=False)
            canvas.create_text(pad + 85 * index, 10, text=label, fill=color, anchor="w")
        canvas.create_text(pad - 5, pad, text=f"{high:.2f}x", anchor="e", fill=self.theme_fg)
        canvas.create_text(pad - 5, height - pad, text=f"{low:.2f}x", anchor="e", fill=self.theme_fg)

    def _close(self):
        if self.research_cancel:
            self.research_cancel.set()
        if self.history_cancel_file:
            try:
                self.history_cancel_file.write_text("cancel", encoding="utf-8")
            except OSError:
                logging.getLogger(__name__).exception("Could not request history update cancellation")
        for engine in self.engines.values():
            try:
                engine.stop()
            except Exception:
                logging.getLogger(__name__).exception("Could not stop paper engine")
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.heavy_executor.shutdown(wait=False, cancel_futures=True)
        self._remove_ui_log_handler()
        self.destroy()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="NEPSE Quant desktop dashboard")
    parser.add_argument("--smoke", action="store_true", help="build all GUI views and exit")
    args = parser.parse_args()
    app = DesktopDashboard(smoke=args.smoke)
    if args.smoke:
        valid = len(app.page_list.get_children("")) == len(PAGES) and len(app.pages) == len(PAGES) and len(app.tables) == 14
        app._populate("Signals", [{"symbol": f"SYM{i:03d}"} for i in range(205)])
        valid = valid and len(app.tables["Signals"].get_children()) == 100
        valid = valid and app.table_pagers["Signals"][0].cget("text") == "1–100 of 205"
        app._change_table_page("Signals", 1)
        valid = valid and len(app.tables["Signals"].get_children()) == 100
        valid = valid and app.tables["Signals"].item(app.tables["Signals"].get_children()[0], "values")[0] == "SYM100"
        app._change_table_page("Signals", 1)
        valid = valid and len(app.tables["Signals"].get_children()) == 5
        app._append_log_entry(logging.WARNING, "History", "Warning sample")
        valid = valid and "WARNING" in app.log_text.get("1.0", "end") and "[History]" in app.log_text.get("1.0", "end")
        app._toggle_log_panel()
        valid = valid and app.log_panel_open and app.log_panel.winfo_manager() == "pack"
        valid = valid and app.log_text.tag_cget("WARNING", "foreground") == "#a15c00"
        app._toggle_log_panel()
        valid = valid and not app.log_panel_open
        app._remove_ui_log_handler()
        app.destroy()
        if not valid:
            return 1
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
