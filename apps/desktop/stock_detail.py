"""Stock detail window and cached price history helpers."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

PRICE_RANGES = ("1M", "3M", "6M", "1Y", "All")


def detail_error_payload(symbol: str, error: object) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "history": pd.DataFrame(),
        "quote": None,
        "report": None,
        "report_error": f"Could not load stock data: {error}",
    }


def load_stock_detail(symbol: str, db_path: Path | None = None) -> dict[str, Any]:
    """Read one stock's stored bars, latest cached quote, and financial report."""
    if db_path is None:
        from backend.quant_pro.database import get_db_path

        db_path = get_db_path()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        bars = pd.read_sql_query(
            "SELECT date,open,high,low,close,volume FROM stock_prices "
            "WHERE symbol=? ORDER BY date ASC",
            conn,
            params=(symbol,),
        )
        try:
            quote = conn.execute(
                "SELECT security_name,last_traded_price,previous_close,"
                "percentage_change,fetched_at_utc FROM market_quotes "
                "WHERE symbol=? ORDER BY fetched_at_utc DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        except sqlite3.OperationalError:
            quote = None
    finally:
        conn.close()

    if bars.empty:
        return {"symbol": symbol, "history": bars, "quote": dict(quote) if quote else None,
                "report": None, "report_error": "No stored price history is available for this symbol."}

    report = None
    report_error = None
    try:
        from backend.quant_pro.stock_report import build_stock_report

        current_price = quote["last_traded_price"] if quote else None
        report = build_stock_report(symbol, float(current_price or bars.iloc[-1]["close"]))
    except Exception as exc:
        report_error = f"Financial report unavailable: {exc}"

    return {
        "symbol": symbol,
        "history": bars,
        "quote": dict(quote) if quote else None,
        "report": report,
        "report_error": report_error,
    }


def prepare_history(history: pd.DataFrame, range_name: str) -> pd.DataFrame:
    """Add full-history moving averages, then select the displayed date range."""
    if history.empty:
        return history.copy()
    data = history.sort_values("date").copy()
    data["ma20"] = data["close"].rolling(20).mean()
    data["ma50"] = data["close"].rolling(50).mean()
    days = {"1M": 30, "3M": 90, "6M": 183, "1Y": 365}.get(range_name)
    if days is None:
        return data.reset_index(drop=True)
    end = pd.to_datetime(data["date"].iloc[-1])
    start = end - pd.Timedelta(days=days)
    return data[pd.to_datetime(data["date"]) >= start].reset_index(drop=True)


def market_metrics(
    history: pd.DataFrame,
    quote: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Format the stored quote and historical range as separate dated metrics."""
    result = {
        "quote": "—", "historical": "—", "session": "—",
        "change": "—", "range": "—", "coverage": "—",
    }
    if history.empty:
        return result

    ordered = history.sort_values("date")
    latest = ordered.iloc[-1]
    asof = str(latest["date"])
    result["historical"] = f"{latest['close']:,.2f} · {asof}"
    result["session"] = (
        f"Open {latest['open']:,.2f} · High {latest['high']:,.2f} · "
        f"Low {latest['low']:,.2f} · Volume {latest['volume']:,.0f} · {asof}"
    )
    notes = []
    if quote and quote.get("last_traded_price") is not None:
        fetched = str(quote.get("fetched_at_utc") or "")
        result["quote"] = f"{float(quote['last_traded_price']):,.2f} · {fetched[:16] or 'date unavailable'} UTC"
        try:
            fetched_at = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            current_time = now or datetime.now(timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
            if current_time - fetched_at > pd.Timedelta(days=2):
                notes.append("cached quote is stale")
        except (ValueError, TypeError):
            notes.append("quote age is unavailable")

    if len(ordered) > 1:
        previous = ordered.iloc[-2]
        if (pd.Timestamp(asof) - pd.Timestamp(previous["date"])).days <= 14 and previous["close"]:
            change = (float(latest["close"]) - float(previous["close"])) / float(previous["close"]) * 100
            result["change"] = f"{change:+.2f}% · {asof}"

    cutoff = pd.Timestamp(asof) - pd.Timedelta(days=365)
    year = ordered[pd.to_datetime(ordered["date"]) >= cutoff]
    if not year.empty:
        result["range"] = f"{year['high'].max():,.2f} / {year['low'].min():,.2f}"

    last_day = date.fromisoformat(asof[:10])
    try:
        from backend.quant_pro.nepse_calendar import latest_completed_session

        if (latest_completed_session() - last_day).days > 14:
            notes.append("stored bars are stale")
    except Exception:
        if (date.today() - last_day).days > 14:
            notes.append("stored bars are stale")
    gaps = pd.to_datetime(ordered["date"]).diff().dt.days
    maximum_gap = int(gaps.max()) if gaps.notna().any() else 0
    if maximum_gap > 14:
        notes.append(f"history has a {maximum_gap}-day gap")
    result["coverage"] = " · ".join(notes) if notes else "Stored history looks current"
    return result


def draw_price_chart(figure: Figure, data: pd.DataFrame, *, line: bool = False) -> None:
    """Draw price bars (or close line), full-history moving averages, and volume."""
    figure.clear()
    price, volume = figure.subplots(
        2, 1, sharex=True, gridspec_kw={"height_ratios": (3, 1)}
    )
    figure.subplots_adjust(left=0.11, right=0.98, top=0.95, bottom=0.13, hspace=0.06)
    if data.empty:
        price.text(0.5, 0.5, "No price history", ha="center", va="center", transform=price.transAxes)
        volume.set_visible(False)
        return

    x = list(range(len(data)))
    dates = pd.to_datetime(data["date"])
    colors = ["#178a54" if close >= open_ else "#d84a4a" for open_, close in zip(data["open"], data["close"])]
    if line:
        price.plot(x, data["close"], color="#1769aa", linewidth=1.5, label="Close")
    else:
        wick_segments = [
            ((index, low), (index, high))
            for index, (low, high) in enumerate(zip(data["low"], data["high"]))
        ]
        price.add_collection(LineCollection(wick_segments, colors=colors, linewidths=1))
        for index, (open_, close) in enumerate(zip(data["open"], data["close"])):
            bottom = min(open_, close)
            height = max(abs(close - open_), max(abs(close), 1) * 0.0001)
            price.add_patch(Rectangle((index - 0.32, bottom), 0.64, height, color=colors[index]))
        price.set_xlim(-1, len(data))
        price.set_ylim(float(data["low"].min()), float(data["high"].max()))
        price.plot([], [], color="#178a54", label="Up day")
        price.plot([], [], color="#d84a4a", label="Down day")

    price.plot(x, data["ma20"], color="#ed9a27", linewidth=1, label="20-session average")
    price.plot(x, data["ma50"], color="#8a5aba", linewidth=1, label="50-session average")
    price.grid(alpha=0.22)
    price.set_ylabel("NPR")
    price.legend(loc="upper left", ncols=2, fontsize="small")
    volume.bar(x, data["volume"], color=colors, width=0.7)
    volume.set_ylabel("Volume")
    volume.grid(axis="y", alpha=0.22)

    ticks = sorted(set(pd.Series(x).iloc[::max(1, len(x) // 6)].tolist() + [x[-1]]))
    volume.set_xticks(ticks, [dates.iloc[index].strftime("%d %b %y") for index in ticks])


class StockDetailWindow:
    """A reusable non-modal Tk window for inspecting one Market symbol."""

    def __init__(
        self,
        parent: tk.Misc,
        load: Callable[[str, Callable[[dict[str, Any]], None]], None],
        on_close: Callable[[], None],
    ):
        self.parent = parent
        self.load = load
        self.on_close = on_close
        self.closed = False
        self.request_id = 0
        self.request_running = False
        self.symbol = ""
        self.payload: dict[str, Any] | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("Stock details · NEPSE Quant")
        self.window.geometry("1160x800")
        self.window.minsize(850, 600)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        shell = ttk.Frame(self.window, padding=12)
        shell.pack(fill="both", expand=True)
        self.title = tk.StringVar(value="Select a stock")
        ttk.Label(shell, textvariable=self.title, font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        self.metrics = tk.StringVar(value="Loading stock data…")
        ttk.Label(shell, textvariable=self.metrics, justify="left", wraplength=1100).pack(anchor="w", pady=(4, 8))

        toolbar = ttk.Frame(shell)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Period").pack(side="left")
        self.range_name = tk.StringVar(value="3M")
        self.range_picker = ttk.Combobox(toolbar, textvariable=self.range_name, values=PRICE_RANGES, state="readonly", width=6)
        self.range_picker.pack(side="left", padx=(5, 12))
        self.range_picker.bind("<<ComboboxSelected>>", lambda _event: self.render_chart())
        self.line_chart = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Close-price line", variable=self.line_chart, command=self.render_chart).pack(side="left")
        self.retry_button = ttk.Button(toolbar, text="Retry", command=self.retry)
        self.retry_button.pack(side="right")

        tabs = ttk.Notebook(shell)
        tabs.pack(fill="both", expand=True)
        chart_tab = ttk.Frame(tabs, padding=4)
        report_tab = ttk.Frame(tabs, padding=8)
        tabs.add(chart_tab, text="Price and volume")
        tabs.add(report_tab, text="Company and financials")
        self.figure = Figure(figsize=(8.2, 5.7), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_tab)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.report_text = tk.Text(report_tab, wrap="word", undo=False)
        report_scroll = ttk.Scrollbar(report_tab, orient="vertical", command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=report_scroll.set, state="disabled")
        self.report_scroll = report_scroll
        report_scroll.pack(side="right", fill="y")
        self.report_text.pack(side="left", fill="both", expand=True)
        draw_price_chart(self.figure, pd.DataFrame(), line=False)
        self.canvas.draw_idle()

    def select(self, symbol: str) -> None:
        self.symbol = symbol.strip().upper()
        self.title.set(f"{self.symbol} · loading…")
        self.payload = None
        self.request_id += 1
        if not self.request_running:
            self._request()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_set()

    def _request(self) -> None:
        self.request_running = True
        requested_symbol = self.symbol
        requested_id = self.request_id

        def done(payload: dict[str, Any]) -> None:
            self.request_running = False
            if self.closed:
                return
            if requested_id != self.request_id:
                self._request()
                return
            self.payload = payload
            self.render()

        self.load(requested_symbol, done)

    def retry(self) -> None:
        if self.closed or self.request_running or not self.symbol:
            return
        self.request_id += 1
        self._request()

    def render(self) -> None:
        if not self.payload:
            return
        history = self.payload["history"]
        quote = self.payload.get("quote")
        report = self.payload.get("report") or {}
        company = report.get("company_name") or (quote or {}).get("security_name") or self.symbol
        sector = report.get("sector") or "—"
        self.title.set(f"{company} ({self.symbol}) · {sector}")
        metrics = market_metrics(history, quote)
        self.metrics.set(
            f"Cached quote: {metrics['quote']}    Historical close: {metrics['historical']}    "
            f"Daily change: {metrics['change']}    52-week high / low: {metrics['range']}\n"
            f"{metrics['session']}\nData coverage: {metrics['coverage']}"
        )
        self.render_chart()
        self._render_report(report, self.payload.get("report_error"), not history.empty)

    def render_chart(self) -> None:
        if not self.payload:
            return
        data = prepare_history(self.payload["history"], self.range_name.get())
        draw_price_chart(self.figure, data, line=self.line_chart.get())
        self.canvas.draw_idle()

    def _render_report(self, report: dict[str, Any], error: str | None, has_history: bool) -> None:
        lines = []
        if not has_history:
            lines.append("Price history unavailable. Check the local market database and retry.")
        if error:
            lines.append(error)
        if report:
            lines.extend((report.get("summary", ""), "", "Financial snapshot"))
            lines.extend(f"{label}: {value}" for label, value in report.get("snapshot", []))
            financial = report.get("financial_rows") or []
            if financial:
                lines.extend(("", "Recent financial periods"))
                for row in financial:
                    lines.append(
                        f"{row.get('period', '—')}: Revenue {row.get('revenue', '—')} · "
                        f"Net profit {row.get('net_profit', '—')} · EPS {row.get('eps', '—')}"
                    )
            for heading, key in (("Positive factors", "positives"), ("Risks to monitor", "risks"), ("Additional monitors", "monitors")):
                values = report.get(key) or []
                if values:
                    lines.extend(("", heading, *(f"• {value}" for value in values)))
        else:
            lines.append("No cached financial report is available. Price history and market statistics can still be reviewed.")
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", "\n".join(lines).strip())
        self.report_text.configure(state="disabled")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.on_close()
        self.window.destroy()
