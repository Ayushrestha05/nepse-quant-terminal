"""Shared HTTPS-only proxy pool for NEPSE scrapers.

Reads ``NQT_PROXIES`` (comma-separated URLs) or fetches public free proxy lists
from GitHub, health-checks candidates over HTTPS against Merolagani, rotates
healthy proxies, and drops dead ones.

In proxy-only mode (``proxy_only=True`` or ``NQT_PROXY_ONLY=1``), raises
``ProxyPoolError`` if no healthy proxy is available — never falls back to a
direct connection from the host IP.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Optional

import requests
from requests.exceptions import RequestException

from backend.quant_pro.paths import get_data_dir

logger = logging.getLogger(__name__)

# Public raw proxy lists (HTTP/HTTPS proxies capable of HTTPS CONNECT tunneling).
PUBLIC_PROXY_SOURCES: tuple[str, ...] = (
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
)

DEFAULT_HEALTH_URL = "https://merolagani.com/"
DEFAULT_HEALTH_MARKER = "merolagani"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
PROXY_CACHE_TTL_SECS = 1800


class ProxyPoolError(RuntimeError):
    """Raised when proxy-only mode cannot obtain a healthy proxy or target is non-HTTPS."""


def is_proxy_only() -> bool:
    raw = (os.environ.get("NQT_PROXY_ONLY") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def parse_proxy_env(env_var: str = "NQT_PROXIES") -> list[str]:
    raw = (os.environ.get(env_var) or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for item in raw.split(","):
        p = _normalize_proxy_url(item)
        if p:
            out.append(p)
    return list(dict.fromkeys(out))


def _normalize_proxy_url(raw: str) -> str:
    s = (raw or "").strip()
    if not s or s.startswith("#"):
        return ""
    if "://" not in s:
        s = f"http://{s}"
    return s


def _ensure_https(url: str) -> None:
    if not str(url).lower().startswith("https://"):
        raise ProxyPoolError(
            f"Refusing non-HTTPS target through untrusted proxy: {url}"
        )


def _cache_file() -> Path:
    return get_data_dir(__file__) / "runtime" / "healthy_proxies.txt"


def _load_cached_proxies(ttl: int = PROXY_CACHE_TTL_SECS) -> list[str]:
    path = _cache_file()
    try:
        if not path.exists():
            return []
        if (time.time() - path.stat().st_mtime) > ttl:
            return []
        lines = [_normalize_proxy_url(x) for x in path.read_text().splitlines()]
        return [p for p in lines if p]
    except OSError:
        return []


def _save_cached_proxies(proxies: list[str]) -> None:
    if not proxies:
        return
    path = _cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(proxies) + "\n")
    except OSError:
        pass


def fetch_public_proxy_candidates(
    sources: Iterable[str] = PUBLIC_PROXY_SOURCES,
    *,
    timeout: float = 10.0,
    max_candidates: int = 400,
) -> list[str]:
    """Download candidate proxy URLs from public GitHub lists."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for src in sources:
        try:
            resp = requests.get(src, timeout=(4.0, timeout), headers={"User-Agent": DEFAULT_UA})
            if resp.status_code != 200:
                continue
            for line in resp.text.splitlines():
                p = _normalize_proxy_url(line)
                if p and p not in seen_set:
                    seen_set.add(p)
                    seen.append(p)
        except Exception as exc:
            logger.debug("Proxy source %s failed: %s", src, exc)
    random.shuffle(seen)
    return seen[:max_candidates]


def _check_one_proxy(
    proxy: str,
    *,
    health_url: str = DEFAULT_HEALTH_URL,
    marker: str = DEFAULT_HEALTH_MARKER,
    timeout: float = 5.0,
) -> bool:
    _ensure_https(health_url)
    try:
        resp = requests.get(
            health_url,
            proxies={"http": proxy, "https": proxy},
            headers={"User-Agent": DEFAULT_UA},
            timeout=(min(2.5, timeout), timeout),
            verify=True,
        )
        if resp.status_code != 200:
            return False
        if marker and marker.lower() not in resp.text.lower():
            return False
        return True
    except Exception:
        return False


class ProxyPool:
    """Thread-safe rotating HTTPS proxy pool with health checks and dead-proxy eviction."""

    # ponytail: file-cached healthy proxy list (30 min TTL); sufficient for local scraper jobs
    def __init__(
        self,
        *,
        proxies: Optional[Iterable[str]] = None,
        proxy_only: Optional[bool] = None,
        auto_fetch: bool = True,
        health_url: str = DEFAULT_HEALTH_URL,
        health_marker: str = DEFAULT_HEALTH_MARKER,
        target_size: int = 12,
        check_timeout: float = 5.0,
        skip_health_check: bool = False,
        use_cache: bool = True,
    ) -> None:
        self.proxy_only = is_proxy_only() if proxy_only is None else bool(proxy_only)
        self.auto_fetch = auto_fetch
        self.health_url = health_url
        self.health_marker = health_marker
        self.target_size = max(1, int(target_size))
        self.check_timeout = float(check_timeout)
        self.skip_health_check = skip_health_check
        self.use_cache = use_cache

        self._lock = threading.Lock()
        self._healthy: list[str] = []
        self._bad: set[str] = set()
        self._idx = 0
        self._last_refresh = 0.0

        seed = (
            [_normalize_proxy_url(p) for p in proxies if _normalize_proxy_url(p)]
            if proxies is not None
            else parse_proxy_env()
        )
        if seed:
            if skip_health_check:
                self._healthy = list(dict.fromkeys(seed))
            else:
                self._healthy = self._health_check_batch(seed)

    def _health_check_batch(self, candidates: list[str], *, wave_size: int = 60) -> list[str]:
        fresh = [p for p in candidates if p and p not in self._bad]
        if not fresh:
            return []
        good: list[str] = []
        for offset in range(0, len(fresh), wave_size):
            wave = fresh[offset : offset + wave_size]
            with ThreadPoolExecutor(max_workers=min(40, len(wave))) as pool:
                futs = {
                    pool.submit(
                        _check_one_proxy,
                        p,
                        health_url=self.health_url,
                        marker=self.health_marker,
                        timeout=self.check_timeout,
                    ): p
                    for p in wave
                }
                for fut in as_completed(futs):
                    p = futs[fut]
                    try:
                        ok = fut.result()
                    except Exception:
                        ok = False
                    if ok:
                        good.append(p)
            if len(good) >= self.target_size:
                break
        logger.info("Proxy health check: %d/%d healthy against %s", len(good), len(fresh), self.health_url)
        return good

    def refresh(self, *, force: bool = False) -> int:
        with self._lock:
            now = time.monotonic()
            if not force and self._healthy and (now - self._last_refresh) < 60:
                return len(self._healthy)
            self._last_refresh = now

        env_candidates = parse_proxy_env()
        if not env_candidates and self.use_cache:
            cached = [p for p in _load_cached_proxies() if p not in self._bad]
            if cached:
                with self._lock:
                    existing = set(self._healthy)
                    for p in cached:
                        if p not in existing:
                            self._healthy.append(p)
                            existing.add(p)
                    if self._healthy:
                        logger.info("Loaded %d cached healthy proxies", len(self._healthy))
                        return len(self._healthy)

        candidates = env_candidates
        if not candidates and self.auto_fetch:
            candidates = fetch_public_proxy_candidates()
        if not candidates:
            return 0
        good = (
            [p for p in candidates if p not in self._bad]
            if self.skip_health_check
            else self._health_check_batch(candidates)
        )
        with self._lock:
            existing = set(self._healthy)
            for p in good:
                if p not in existing and p not in self._bad:
                    self._healthy.append(p)
                    existing.add(p)
            if self._healthy and self.use_cache and not env_candidates:
                _save_cached_proxies(self._healthy)
            return len(self._healthy)

    def size(self) -> int:
        with self._lock:
            return len(self._healthy)

    def next_proxy(self) -> Optional[str]:
        with self._lock:
            if self._healthy:
                p = self._healthy[self._idx % len(self._healthy)]
                self._idx += 1
                return p
        if self.auto_fetch or parse_proxy_env():
            self.refresh(force=True)
            with self._lock:
                if self._healthy:
                    p = self._healthy[self._idx % len(self._healthy)]
                    self._idx += 1
                    return p
        if self.proxy_only:
            raise ProxyPoolError(
                "No healthy HTTPS proxies available; direct fallback is disabled (proxy_only=True)."
            )
        return None

    def mark_bad(self, proxy: str) -> None:
        with self._lock:
            self._bad.add(proxy)
            if proxy in self._healthy:
                self._healthy.remove(proxy)

    def request(
        self,
        method: str,
        url: str,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 20.0,
        max_attempts: int = 8,
        **kwargs,
    ) -> requests.Response:
        """Send an HTTPS request through a rotating proxy; never falls back to direct in proxy_only mode."""
        _ensure_https(url)
        requester = session.request if session is not None else requests.request
        kwargs.setdefault("verify", True)
        req_timeout = (min(5.0, float(timeout)), float(timeout)) if isinstance(timeout, (int, float)) else timeout

        last_exc: Optional[BaseException] = None
        for _ in range(max(1, int(max_attempts))):
            proxy = self.next_proxy()
            if proxy is None:
                if self.proxy_only:
                    raise ProxyPoolError("Proxy required but none available.")
                return requester(method, url, timeout=req_timeout, **kwargs)

            req_kwargs = dict(kwargs)
            req_kwargs["proxies"] = {"http": proxy, "https": proxy}
            try:
                resp = requester(method, url, timeout=req_timeout, **req_kwargs)
                if resp.status_code in (403, 407, 429, 502, 503, 504):
                    self.mark_bad(proxy)
                    last_exc = RequestException(f"HTTP {resp.status_code} via {proxy}")
                    continue
                return resp
            except RequestException as exc:
                self.mark_bad(proxy)
                last_exc = exc
                continue

        if self.proxy_only:
            raise ProxyPoolError(
                f"All {max_attempts} proxied attempts failed for {url}; direct fallback disabled: {last_exc}"
            ) from last_exc
        if last_exc is not None:
            raise last_exc
        raise ProxyPoolError(f"Failed to fetch {url}")

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)


_default_lock = threading.Lock()
_default_pool: Optional[ProxyPool] = None


def get_proxy_pool(*, proxy_only: Optional[bool] = None, reset: bool = False) -> ProxyPool:
    """Return process-wide shared ProxyPool."""
    global _default_pool
    with _default_lock:
        want_only = is_proxy_only() if proxy_only is None else bool(proxy_only)
        if reset or _default_pool is None or _default_pool.proxy_only != want_only:
            _default_pool = ProxyPool(proxy_only=want_only)
        return _default_pool
