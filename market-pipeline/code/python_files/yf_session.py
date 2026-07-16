#!/usr/bin/env python3
"""
yf_session.py — shared yfinance session/config + rate-limit backoff helper
for the bulk-fetch scripts (cross_sectional_momentum.py, earnings_calendar.py,
earnings_key_dates.py, earnings_dates_cache.py).

BACKGROUND / WHY THIS MODULE LOOKS THE WAY IT DOES
----------------------------------------------------
The classic community fix for yfinance rate-limiting is "pass yfinance a
curl_cffi session with impersonate='chrome' so it doesn't look like a bot".
Investigated 2026-07-16 against the installed yfinance==1.2.0
(.venv/lib/python3.9/site-packages/yfinance): that fix is ALREADY yfinance
1.2.0's default behavior.

  yfinance/base.py:
      self.session = session or requests.Session(impersonate="chrome")
  yfinance/data.py (YfData singleton, shared by every Ticker/download call):
      self._set_session(session or requests.Session(impersonate="chrome"))

  (`requests` there is `curl_cffi.requests`, imported at the top of both
  files — yfinance 1.2.0 vendors curl_cffi internally, it does not use
  plain `requests` any more.)

So explicitly building another curl_cffi(impersonate="chrome") session and
handing it to Ticker() produces a session functionally identical to the one
yfinance would have constructed on its own. There is no TLS/HTTP2
fingerprint problem left to fix here.

EMPIRICAL TEST (2026-07-16, same session that hit the block):
  - cache_seed/earnings_dates_cache_log.txt shows the real failure: at
    ~11:42-11:49 IST, get_earnings_dates() batches returned 0/680 (US),
    0/647 (JP), 0/579 (KR) — every single request in those batches failed.
  - Re-running the IDENTICAL default-session code path (no curl_cffi
    session override) ~15-20 minutes later:
      * yf.Ticker(x).info for AAPL/MSFT/7203.T/005930.KS/RELIANCE.NS: 5/5 OK
      * 300 US symbols via the real parallel_map(workers=8) pattern: 300/300
        OK, 0 errors, 12.1s
      * ec.fetch_calendar("JP", 120 real symbols) via the actual production
        _fetch_one: 114/120 got results (misses were genuine "no earnings
        data" tickers, not rate limits), 21s
      * ec.fetch_calendar("KR", 120 real symbols): 97/120, 16.7s
  - Conclusion: the block was time/IP-based and had already cleared on its
    own by the time of the second test. curl_cffi impersonation (already
    default) was never the variable — switching sessions would not have
    unblocked the first, still-blocked run.

THE ACTUAL GAP, and what this module fixes
--------------------------------------------
Reading yfinance/data.py's `_make_request()`: transient network errors
(timeouts, connection errors) get retried up to `YfConfig.network.retries`
times with 2**attempt backoff — but a 429 does NOT go through that path.
`_get_cookie_and_crumb()` / `_make_request()` raise YFRateLimitError()
immediately on the first 429, with zero retry and zero backoff.

Combined with how the three target scripts call yfinance — a bare
`try: ... except Exception: return None` inside `_fetch_one`, run under
`parallel_map`'s 8-worker ThreadPoolExecutor — this means: the instant
Yahoo starts 429-ing, every one of the ~600-700 in-flight/queued requests
fails immediately and permanently for that run (hence "0/647"). There is
no backoff to let the rate-limit window reset, and re-running the whole
script just re-hammers Yahoo again while still blocked.

So the real, evidence-backed mitigation is: retry specifically on
YFRateLimitError with exponential backoff + jitter, and give bulk-fetch
loops a way to throttle themselves so they're less likely to trip the
limit in the first place. Both are implemented below.

USAGE
-----
    from yf_session import configure_yfinance, call_with_backoff

    configure_yfinance()          # call once per process, at script startup

    def _fetch_one(args):
        market, symbol = args
        try:
            import yfinance as yf
            info = call_with_backoff(lambda: yf.Ticker(_yf_ticker(market, symbol)).info)
            ...
        except Exception:
            return None

`configure_yfinance()` is idempotent and safe to call from every worker
thread / every script that imports this module — only the first call does
anything.
"""

from __future__ import annotations

import random
import threading
import time

_configured = False
_configure_lock = threading.Lock()

_throttle_lock = threading.Lock()
_last_call_ts = 0.0

DEFAULT_IMPERSONATE = "chrome"


def configure_yfinance(impersonate: str = DEFAULT_IMPERSONATE,
                        retries: int = 2,
                        proxy: str | None = None) -> None:
    """Idempotent one-time yfinance setup. Safe to call from every script /
    every worker thread; only the first call takes effect.

    - Installs an explicit curl_cffi(impersonate=...) session onto
      yfinance's shared YfData singleton. NOTE: this is functionally a
      no-op against yfinance 1.2.0's own default (it already builds an
      identical curl_cffi(impersonate="chrome") session internally — see
      module docstring). Kept explicit anyway so (a) the impersonation
      target / a proxy can be changed from one place if ever needed, and
      (b) behavior doesn't silently depend on yfinance's internal default
      if a future yfinance version changes it.
    - Sets YfConfig.network.retries, which controls yfinance's built-in
      retry of *transient* errors (timeouts/connection errors) only — it
      does NOT cover HTTP 429. Use call_with_backoff() for that.
    - Optionally sets a proxy.
    """
    global _configured
    with _configure_lock:
        if _configured:
            return
        import yfinance as yf
        from curl_cffi import requests as curl_requests
        from yfinance.data import YfData

        session = curl_requests.Session(impersonate=impersonate)
        YfData(session=session)  # same idiom yfinance's own multi.py uses internally

        yf.config.network.retries = retries
        if proxy:
            yf.config.network.proxy = proxy

        _configured = True


def throttle(min_interval: float) -> None:
    """Optional global pacing: block the calling thread until at least
    `min_interval` seconds have passed since the last throttled call
    process-wide. Off by default (min_interval=0 is a no-op) — pass e.g.
    0.1-0.2 to call_with_backoff() if 429s start recurring and
    backoff-retry alone isn't enough headroom.
    """
    if min_interval <= 0:
        return
    global _last_call_ts
    with _throttle_lock:
        now = time.monotonic()
        wait = _last_call_ts + min_interval - now
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()


def call_with_backoff(fn, max_attempts: int = 4, base_delay: float = 5.0,
                       max_delay: float = 60.0, min_interval: float = 0.0):
    """Call fn() (a zero-arg callable wrapping one yfinance request),
    retrying specifically on YFRateLimitError (HTTP 429) with exponential
    backoff + jitter — the retry yfinance itself does not do for 429s.

    Any other exception propagates immediately (unchanged behavior for
    non-rate-limit failures like delisted/missing-data symbols).
    Re-raises the rate-limit error if all attempts are exhausted, so
    callers' existing `except Exception: return None` continues to work
    unmodified.
    """
    from yfinance.exceptions import YFRateLimitError

    last_exc = None
    for attempt in range(max_attempts):
        throttle(min_interval)
        try:
            return fn()
        except YFRateLimitError as e:
            last_exc = e
            if attempt == max_attempts - 1:
                raise
            delay = min(max_delay, base_delay * (2 ** attempt)) + random.uniform(0, 1.0)
            time.sleep(delay)
    raise last_exc  # pragma: no cover — loop always returns or raises above


def get_session(impersonate: str = DEFAULT_IMPERSONATE):
    """Factory for callers that want to pass a session explicitly, e.g.
    `yf.Ticker(sym, session=get_session())`. Equivalent to what yfinance
    1.2.0 builds by default — provided for explicitness / future-proofing,
    not because the default is broken."""
    from curl_cffi import requests as curl_requests
    return curl_requests.Session(impersonate=impersonate)
