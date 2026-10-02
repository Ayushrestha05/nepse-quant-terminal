"""Compact Tk desktop dashboard for NEPSE Quant."""

from __future__ import annotations

import json
import logging
import math
import os
import queue
import sqlite3
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
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
    return view.where(view.notna(), None).to_dict(orient="records")


class DesktopDashboard(tk.Tk):
    """Tk interface; expensive data loads and all simulations run in workers."""

    def __init__(self, *, smoke: bool = False):
        super().__init__()
        self.title("NEPSE Quant")
        self.geometry("1240x820")
        self.minsize(920, 620)
        self.smoke = smoke
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nepse-ui")
        self.ui_events: queue.SimpleQueue = queue.SimpleQueue()
        self.jobs: dict[str, Any] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.tables: dict[str, ttk.Treeview] = {}
        self.table_columns: dict[str, tuple[str, ...]] = {}
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
        self.strategy_payloads: dict[str, dict[str, Any]] = {}
        self.account_var = tk.StringVar(value="Loading accounts…")
        self.app_status = tk.StringVar(value="Ready")
        self._build_shell()
        if not smoke:
            self._init_runtime()
            self.after(50, self._poll_ui_events)
            self.after(50, self._load_current_page)
            self.after(60_000, self._auto_refresh)
        else:
            for name in PAGES:
                self.pages[name] = self._build_page(name)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_shell(self) -> None:
        style = ttk.Style(self)
        style.configure("TNotebook.Tab", padding=(8, 4))
        style.configure("Treeview", rowheight=22)
        style.configure("Treeview.Heading", font=("TkDefaultFont", 9, "bold"))

        header = ttk.Frame(self, padding=(10, 8, 10, 6))
        header.pack(fill="x")
        ttk.Label(header, text="NEPSE QUANT", font=("TkDefaultFont", 15, "bold")).pack(side="left")
        ttk.Label(header, text="PAPER TRADING", padding=(12, 0)).pack(side="left")
        self.account_picker = ttk.Combobox(header, textvariable=self.account_var, width=25, state="readonly")
        self.account_picker.pack(side="right", padx=(6, 0))
        self.account_picker.bind("<<ComboboxSelected>>", self._account_changed)
        ttk.Button(header, text="Refresh", command=lambda: self._load_page(self.current_page, force=True)).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        nav = ttk.Frame(body, padding=(0, 0, 8, 0))
        content = ttk.Frame(body)
        body.add(nav, weight=0)
        body.add(content, weight=1)
        self.page_list = tk.Listbox(nav, width=22, exportselection=False, activestyle="dotbox", borderwidth=0, highlightthickness=0)
        for label in PAGES:
            self.page_list.insert("end", label)
        self.page_list.pack(fill="both", expand=True)
        self.page_list.selection_set(0)
        self.page_list.bind("<<ListboxSelect>>", self._page_selected)
        self.content = content
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        ttk.Label(self, textvariable=self.app_status, anchor="w", padding=(10, 4)).pack(fill="x")

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
            if event[0] == "status":
                self.app_status.set(event[1])
            elif event[0] == "refresh":
                self._load_page(event[1], force=True)
            elif event[0] == "background":
                _, key, done, payload, error = event
                self._finish_background(key, done, payload, error)
            elif event[0] == "research_progress":
                self._research_progress(event[1])
        self.after(100, self._poll_ui_events)

    def _page_selected(self, _event=None) -> None:
        selection = self.page_list.curselection()
        if not selection:
            return
        self.current_page = PAGES[selection[0]]
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
        table.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tables[name] = table
        return table

    def _detail(self, parent, name: str, height: int = 7) -> tk.Text:
        widget = tk.Text(parent, height=height, wrap="word", undo=False)
        widget.pack(fill="both", expand=True, pady=(6, 0))
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
        table = self.tables.get(name)
        if table:
            table.delete(*table.get_children())
            keys = self.table_columns[name]
            for row in rows:
                values = [row.get(key, "") for key in keys]
                table.insert("", "end", values=tuple("" if value is None else value for value in values))
        if name in self.status_vars:
            self.status_vars[name].set(status or f"{len(rows):,} rows")
        if detail:
            self._set_detail(name, detail)

    def _build_market(self, frame):
        self._table(frame, "Market", (("symbol", "Symbol", 110), ("close", "Close", 100), ("chg", "Change %", 100), ("volume", "Volume", 110), ("turn", "Turnover", 120)), height=24)

    def _build_portfolio(self, frame):
        self._table(frame, "Portfolio", (("symbol", "Symbol", 100), ("shares", "Shares", 80), ("entry", "Entry", 90), ("last", "Last", 90), ("value", "Market Value", 130), ("pnl", "Unrealized P/L", 125), ("pnl_pct", "P/L %", 80)), height=18)
        self._detail(frame, "Portfolio", height=8)

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
        self.strategy_editor = tk.Text(right, wrap="none", undo=True)
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
        self.research_chart = tk.Canvas(frame, height=185, background="white", highlightthickness=1, highlightbackground="#c8c8c8")
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

    def _build_page(self, name: str) -> tk.Frame:
        frame = ttk.Frame(self.content, padding=8)
        self.status_vars[name] = tk.StringVar(value="Select Refresh to load")
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
        }
        if name in {"Lookup", "Model Research"}:
            if name not in self.loaded:
                self.loaded.add(name)
                if name == "Model Research":
                    self._set_research_status("Ready; choose a date range and run the comparison.")
            return
        self.status_vars[name].set("Loading…")
        if name == "Rates & Commodities":
            self.status_vars[name].set("Fetching market rates…")
        account_id = self.current_account_id
        if name in {"Portfolio", "Signals", "Orders", "Watchlist"}:
            loader = lambda: loaders[name](account_id)
        else:
            loader = loaders[name]
        self._background(f"load:{name}", loader, lambda payload: self._loaded_page(name, payload))
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
        elif name == "Portfolio":
            self._populate(name, payload["rows"], status=payload["summary"], detail=payload["detail"])
        elif name == "Signals":
            self._populate(name, payload["rows"], status=payload["status"])
        elif name == "Lookup":
            self._populate(name, payload["rows"], status=payload["status"], detail=payload["detail"])
        elif name == "Agents":
            self._populate(name, payload["rows"], status=payload["status"], detail=payload["detail"])
        else:
            self._populate(name, payload["rows"], status=payload.get("status", ""))
        self.app_status.set(f"{name} updated")

    def _background(self, key: str, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        future = self.executor.submit(work)
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
            if target in self.status_vars:
                self.status_vars[target].set(f"Error: {error}")
            self.app_status.set(f"{target}: {error}")
            return
        if done:
            done(payload)

    def _auto_refresh(self):
        if not self.smoke and not self.research_cancel:
            self.loaded.discard(self.current_page)
            self._load_page(self.current_page, force=True)
        self.after(60_000, self._auto_refresh)

    def _load_market(self):
        from backend.quant_pro.dashboard_data import MD

        market = MD(top_n=40)
        frame = market.df.copy()
        if frame.empty or not set(("symbol", "close", "chg", "volume", "turn")).issubset(frame.columns):
            return {"rows": [], "summary": f"Market data unavailable · {market.err or 'No cached session'}"}
        if not frame.empty:
            frame = frame.sort_values("chg", ascending=False)
        summary = f"Session {market.latest}    NEPSE breadth: {market.adv} up / {market.dec} down / {market.unch} unchanged"
        return {"rows": _rows(frame[["symbol", "close", "chg", "volume", "turn"]], 100), "summary": summary}

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
        trades = pd.read_csv(service.trade_log_file).tail(10) if service.trade_log_file.exists() else pd.DataFrame()
        detail = "Recent paper trades\n" + (trades.to_string(index=False) if not trades.empty else "No trades recorded.")
        summary = f"{self._account(account_id)['name']}  |  Cash NPR {state['cash']:,.0f}  |  NAV NPR {state['nav']:,.0f}  |  {len(rows)} positions"
        return {"rows": rows, "summary": summary, "detail": detail, "account_id": account_id}

    def _load_signals(self, account_id: str):
        from backend.backtesting.simple_backtest import load_all_prices
        from backend.trading import strategy_registry
        from backend.trading.live_trader import generate_signals
        from configs.long_term import LONG_TERM_CONFIG

        strategy = strategy_registry.load_strategy(str(self._account(account_id).get("strategy_id") or ""))
        config = dict((strategy or {}).get("config") or LONG_TERM_CONFIG)
        conn = sqlite3.connect(str(self._db_path()))
        try:
            prices = load_all_prices(conn)
        finally:
            conn.close()
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
        return {"rows": list(state["open_orders"]) + list(state["order_history"][-100:]), "status": f"{len(state['open_orders'])} open paper orders · no broker connection", "account_id": account_id}

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

        init_kalimati_db()
        commodities, status = refresh_kalimati()
        rows = [{"item": row.get("name_english"), "price": row.get("avg"), "change": row.get("change_pct"), "unit": row.get("unit"), "date": row.get("date")} for row in commodities]
        metals = _fetch_gold_silver_prices() or {}
        for label in ("gold", "silver"):
            price = metals.get(f"{label}_per_tola")
            if price:
                rows.append({"item": label.title(), "price": price, "change": "", "unit": "NPR/tola", "date": metals.get("date_bs", "")})
        noc = _fetch_noc_fuel_prices() or {}
        for key, label in (("petrol", "Petrol"), ("diesel", "Diesel"), ("kerosene", "Kerosene"), ("lpg", "LPG")):
            if noc.get(key):
                rows.append({"item": f"NOC {label}", "price": noc[key], "change": "", "unit": "NPR/litre" if key != "lpg" else "NPR/cylinder", "date": noc.get("date_bs", "")})
        for record in (_fetch_yahoo_futures_price("CL=F", "Crude oil"), _fetch_yahoo_futures_price("GC=F", "Gold futures")):
            if record:
                rows.append({"item": record.get("label") or record.get("name", "Global rate"), "price": record.get("value"), "change": record.get("change_pct", ""), "unit": record.get("unit", ""), "date": record.get("date", "")})
        for record in _fetch_nrb_forex_rates():
            rows.append({"item": f"NPR / {record.get('currency_code', '')}", "price": record.get("sell_rate") or record.get("buy_rate"), "change": record.get("change_pct", ""), "unit": record.get("currency_name", ""), "date": record.get("date", "")})
        return {"rows": rows, "status": status or f"{len(rows)} market rates"}

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

            detail = MD(top_n=0).detail(symbol, limit=40)
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
            values = self._watchlist_values()
            if not any(row["symbol"] == symbol for row in values):
                values.append({"kind": "stock", "key": f"stock:{symbol}", "label": symbol, "symbol": symbol})
                self._save_watchlist(values)
            self.watch_symbol.set("")
            self.loaded.discard("Watchlist")
            self._load_page("Watchlist", force=True)

    def _watch_remove(self):
        table = self.tables["Watchlist"]
        selected = table.selection()
        if selected:
            symbol = table.item(selected[0], "values")[0]
            self._save_watchlist([row for row in self._watchlist_values() if row["symbol"] != symbol])
            self.loaded.discard("Watchlist")
            self._load_page("Watchlist", force=True)

    def _create_account(self):
        from datetime import datetime
        from apps.tui.io.persistence import _account_dir, _blank_account_files, _load_accounts_registry, _save_accounts_registry
        from backend.trading import strategy_registry

        name = simpledialog.askstring("New paper account", "Account name", parent=self)
        if not name or not name.strip():
            return
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

    def _set_nav(self):
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
        except Exception as exc:
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
        try:
            from backend.trading import strategy_registry

            payload = json.loads(self.strategy_editor.get("1.0", "end"))
            saved = strategy_registry.save_custom_strategy(payload)
            self.loaded.discard("Strategies")
            self._load_page("Strategies", force=True)
            self.app_status.set(f"Saved custom strategy {saved['name']} ({saved['id']})")
        except Exception as exc:
            messagebox.showerror("Invalid strategy", str(exc), parent=self)

    def _assign_strategy(self):
        selected = self.tables["Strategies"].selection()
        if not selected:
            messagebox.showinfo("Strategies", "Select a strategy first.", parent=self)
            return
        strategy_id = str(self.tables["Strategies"].item(selected[0], "values")[0])
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
        self._background("strategy_backtest", lambda: self._strategy_backtest(strategy_id, start, end), lambda result: self._set_detail("Strategy result", json.dumps(result, indent=2, default=str)))

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
        self._background("research", work, self._research_complete)

    def _research_progress(self, payload):
        if "progress_pct" in payload:
            self.research_progress.configure(value=payload["progress_pct"])
        self._set_research_status(payload.get("message") or payload.get("phase") or payload.get("stage") or "Running…")

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
        self._populate("Research trades", trades[:1000], status=f"Showing {min(len(trades), 1000):,} of {len(trades):,} trades; full data is in latest.json")

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
        canvas.create_line(pad, height - pad, width - 10, height - pad, fill="#bbbbbb")
        canvas.create_line(pad, pad, pad, height - pad, fill="#bbbbbb")
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
        canvas.create_text(pad - 5, pad, text=f"{high:.2f}x", anchor="e", fill="#555555")
        canvas.create_text(pad - 5, height - pad, text=f"{low:.2f}x", anchor="e", fill="#555555")

    def _close(self):
        if self.research_cancel:
            self.research_cancel.set()
        for engine in self.engines.values():
            try:
                engine.stop()
            except Exception:
                logging.getLogger(__name__).exception("Could not stop paper engine")
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="NEPSE Quant desktop dashboard")
    parser.add_argument("--smoke", action="store_true", help="build all GUI views and exit")
    args = parser.parse_args()
    app = DesktopDashboard(smoke=args.smoke)
    if args.smoke:
        valid = len(app.page_list.get(0, "end")) == len(PAGES) and len(app.pages) == len(PAGES) and len(app.tables) == 12
        app.destroy()
        if not valid:
            return 1
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
