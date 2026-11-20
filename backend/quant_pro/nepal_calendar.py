"""Nepali (Bikram Sambat) calendar helpers for NEPSE strategies and SIP schedules.

Uses `nepdate` (`nepdate-core`) for BS/AD conversion and `nepdate_patro`
(`nepdate-patro`) for Dashain/Tihar event dates (coverage BS 2077-2084).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Iterable, List, Sequence, Tuple

from nepdate import Lang, NepaliDate
from nepdate_patro import coverage as patro_coverage
from nepdate_patro import info as patro_info

# Public annual Nepal Rastra Bank (NRB) Monetary Policy release dates (AD).
NRB_POLICY_DATES: Tuple[date, ...] = (
    date(2016, 7, 14),  # FY 2073/74
    date(2017, 7, 9),   # FY 2074/75
    date(2018, 7, 12),  # FY 2075/76
    date(2019, 7, 24),  # FY 2076/77
    date(2020, 7, 17),  # FY 2077/78
    date(2021, 8, 13),  # FY 2078/79
    date(2022, 7, 22),  # FY 2079/80
    date(2023, 7, 23),  # FY 2080/81
    date(2024, 7, 26),  # FY 2081/82
    date(2025, 7, 11),  # FY 2082/83
    date(2026, 7, 17),  # FY 2083/84
)


def _to_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)[:10]).date()


def to_bs(ad_date: date | datetime | str) -> NepaliDate:
    """Convert an AD date (or datetime/ISO string) to a Bikram Sambat NepaliDate."""
    return NepaliDate.from_date(_to_date(ad_date))


def bs_month_starts(trading_days: Sequence[date | datetime | str]) -> List[date]:
    """Return the first trading day of each BS (year, month) in `trading_days`.

    Preserves chronological order. Expects sorted trading days (sorts defensively).
    """
    dates = sorted({_to_date(d) for d in trading_days})
    starts: List[date] = []
    seen_ym: set[Tuple[int, int]] = set()
    for d in dates:
        bs = NepaliDate.from_date(d)
        ym = (bs.year, bs.month)
        if ym not in seen_ym:
            seen_ym.add(ym)
            starts.append(d)
    return starts


def ashad_end_dates(start_bs_year: int = 2072, end_bs_year: int = 2085) -> List[date]:
    """Return AD dates for the last day of Ashad (BS month 3, Nepal fiscal year-end)."""
    out: List[date] = []
    for bs_year in range(start_bs_year, end_bs_year + 1):
        out.append(NepaliDate(bs_year, 3, 1).last_of_month().to_date())
    return out


@lru_cache(maxsize=4)
def festival_windows(festival: str) -> Tuple[Tuple[date, date], ...]:
    """Return `(start_ad, end_ad)` windows for `'dashain'` or `'tihar'` from `nepdate_patro`.

    - `'dashain'`: Ghatasthapana -> Vijaya Dashami
    - `'tihar'`: Kag Tihar -> Bhai Tika
    """
    fest = festival.strip().lower()
    if fest not in {"dashain", "tihar"}:
        raise ValueError(f"Unsupported festival {festival!r}; expected 'dashain' or 'tihar'")

    cov = patro_coverage()
    cur = cov.start.to_date()
    end = cov.end.to_date()

    by_year: dict[int, dict[str, date]] = {}
    while cur <= end:
        nd = NepaliDate.from_date(cur)
        ci = patro_info(nd)
        for ev in ci.events:
            lbl = ev.label(Lang.EN).lower()
            yr = by_year.setdefault(nd.year, {})
            if fest == "dashain":
                if "ghatasthapana" in lbl and "start" not in yr:
                    yr["start"] = cur
                elif "vijaya dashami" in lbl:
                    yr["end"] = cur
            else:
                if "kag tihar" in lbl and "start" not in yr:
                    yr["start"] = cur
                elif "bhai tika" in lbl:
                    yr["end"] = cur
        cur += timedelta(days=1)

    windows: List[Tuple[date, date]] = []
    for bs_year in sorted(by_year):
        entry = by_year[bs_year]
        if "start" in entry and "end" in entry and entry["start"] <= entry["end"]:
            windows.append((entry["start"], entry["end"]))
    return tuple(windows)


def is_in_days_before(target_date: date, event_dates: Iterable[date], min_days: int, max_days: int) -> bool:
    """True if `min_days <= (event - target_date).days <= max_days` for any event."""
    for ev in event_dates:
        delta = (ev - target_date).days
        if min_days <= delta <= max_days:
            return True
    return False
