#!/usr/bin/env python3
# liquidity.py
# ============
# Liquidity pre-filter — rank/screen every symbol by USD trading turnover so the
# expensive strategy logic only runs on TRADABLE names. Computes each stock's
# 20-day median turnover (Close×Volume), FX-converts to USD, and caches a small
# index (cache_seed/liquidity_index.parquet) for instant filtering.
#
#   from liquidity import liquid_symbols, build_index, turnover
#   syms = liquid_symbols("IN", min_usd=1_000_000)   # only liquid IN names
#
# Why it's faster: screens like custom_screen/run_global_analysis otherwise touch
# the full universe (e.g. India 8,931 stocks, most untradable micro-caps). Filtering
# to liquid names first cuts that to the few hundred that matter — often a 10–20×
# reduction in stocks scored.

from __future__ import annotations

import datetime as _dt
import json
import os
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

INDEX_PATH = Path(__file__).parent / "cache_seed" / "liquidity_index.parquet"

# market -> currency; LSE quotes pence, JSE cents → divide turnover by unit
CCY = {"US": "USD", "IN": "INR", "CN": "CNY", "JP": "JPY", "EU": "EUR", "HK": "HKD",
       "KR": "KRW", "TW": "TWD", "CA": "CAD", "UK": "GBP", "DE": "EUR", "AU": "AUD",
       "SG": "SGD", "SA": "SAR", "BR": "BRL", "CH": "CHF", "ZA": "ZAR", "SE": "SEK",
       "FI": "EUR", "DK": "DKK"}
UNIT = {"UK": 100.0, "ZA": 100.0}


# ── ticker-suffix currency map (for scans that mix currencies in ONE universe) ─
# The market-keyed CCY/UNIT above works for screener_kit's per-market seeds, where
# London sits in its own "UK" seed and UNIT["UK"]=100 unwinds pence. The daily
# pipeline's Europe scan is different: full_european_market_scan.py runs all ~966
# tickers across 17 exchanges in ONE pass with no market split, so currency has to
# come from the ticker suffix instead.
#
# The trap this exists to stop: **London quotes in PENCE, not pounds.** Measured
# 2026-07-15, median LTP is 416 on `.L` vs 72 on `.PA` and 22 on `.MI` — treating
# `.L` as EUR/GBP without the /100 overstates London turnover 100x, and `.L` is
# 426 of the European universe (its largest bloc). Tel Aviv (agorot) and
# Johannesburg (cents) share the convention.
CCY_BY_SUFFIX = {
    ".L": "GBp", ".IL": "GBp",
    ".DE": "EUR", ".F": "EUR", ".PA": "EUR", ".AS": "EUR", ".BR": "EUR",
    ".LS": "EUR", ".IR": "EUR", ".MI": "EUR", ".MC": "EUR", ".HE": "EUR",
    ".VI": "EUR", ".AT": "EUR", ".TL": "EUR", ".RG": "EUR", ".VS": "EUR",
    ".SW": "CHF", ".ST": "SEK", ".OL": "NOK", ".CO": "DKK", ".WA": "PLN",
    ".IS": "TRY", ".PR": "CZK", ".BD": "HUF", ".IC": "ISK",
    ".T": "JPY", ".KS": "KRW", ".KQ": "KRW", ".NS": "INR", ".BO": "INR",
    ".HK": "HKD", ".SS": "CNY", ".SZ": "CNY", ".TW": "TWD", ".SI": "SGD",
    ".TA": "ILA", ".JO": "ZAc", ".AX": "AUD", ".TO": "CAD", ".SA": "BRL",
}
# quote sub-units -> (real currency, divisor)
SUBUNIT = {"GBp": ("GBP", 100.0), "ILA": ("ILS", 100.0), "ZAc": ("ZAR", 100.0)}


def currency_for(ticker: str) -> str:
    """Quote currency from a yfinance ticker suffix. Bare symbol => US (USD)."""
    t = str(ticker)
    if "." in t:
        return CCY_BY_SUFFIX.get("." + t.rsplit(".", 1)[1], "USD")
    return "USD"


def turnover_usd_for(df, ticker: str, fx: Dict[str, float]) -> float:
    """Median daily Close*Volume for one symbol, converted to USD.

    `fx` maps currency -> units per 1 USD (the shape _fx_rates returns).
    Sub-unit quotes (GBp/ILA/ZAc) are divided out before conversion.
    """
    if df is None or not hasattr(df, "columns"):
        return 0.0
    if "Close" not in df.columns or "Volume" not in df.columns:
        return 0.0
    try:
        tv = float((df["Close"] * df["Volume"]).median())
    except Exception:
        return 0.0
    if tv != tv or tv <= 0:                       # NaN / empty
        return 0.0
    ccy = currency_for(ticker)
    if ccy in SUBUNIT:
        ccy, div = SUBUNIT[ccy]
        tv /= div
    rate = fx.get(ccy)
    if not rate or rate <= 0:
        return 0.0
    return tv / rate


# ── Amihud (2002) price impact ────────────────────────────────────────────────
# ILLIQ = mean( |daily return| / daily USD turnover ), the field-standard measure
# of price impact: "the daily price response associated with one dollar of
# trading volume" (Amihud 2002, J. Financial Markets 5:31-56).
#
# WHY BOTH THIS AND TURNOVER: they answer different questions. Turnover is a size
# proxy — how much money changes hands. ILLIQ is a COST proxy — how far the price
# moves when it does. Two stocks can turn over the same USD while one absorbs an
# order silently and the other gaps 4%. The gate below (which the user set at
# Rs 1 crore/day) is trying to control the second thing using the first, so ILLIQ
# is what the gate actually means. It needs no new data: Close and Volume only,
# which every market already carries.
#
# Amihud's own finding is why this matters here: illiquid stocks earn HIGHER
# returns (the illiquidity premium), and the effect is strongest in small firms.
# So a screener that ranks on raw momentum will keep steering into the illiquid
# tail and calling it alpha. ILLIQ makes that visible as a cost rather than
# leaving it to look like an edge.
#
# Scaled by 1e6 so values land in readable units rather than 1e-9.
ILLIQ_SCALE = 1e6


def amihud_illiq(df, ticker: str, fx: Dict[str, float], min_days: int = 60):
    """Amihud ILLIQ (price impact per USD1m traded). None when unmeasurable.

    Days with zero volume are dropped, not treated as zero impact — an untraded
    day carries no information about price impact, and keeping it as 0 would make
    a stock that barely trades look like the most liquid name in the book.
    """
    if not measurable(df):
        return None
    try:
        close = pd.to_numeric(df["Close"], errors="coerce")
        vol = pd.to_numeric(df["Volume"], errors="coerce")
        ret = close.pct_change().abs()
        dvol = close * vol
        ok = ret.notna() & (dvol > 0) & dvol.notna()
        if int(ok.sum()) < min_days:
            return None
        ccy = currency_for(ticker)
        div = 1.0
        if ccy in SUBUNIT:
            ccy, div = SUBUNIT[ccy]
        rate = fx.get(ccy)
        if not rate or rate <= 0:
            return None
        dvol_usd = dvol[ok] / div / rate
        illiq = float((ret[ok] / dvol_usd).mean() * ILLIQ_SCALE)
    except Exception:
        return None
    if illiq != illiq or illiq < 0:
        return None
    return illiq


# ── scan-facing gate ──────────────────────────────────────────────────────────
# One USD bar across every market, so "tradeable" means the same thing whether the
# stock is in Mumbai or Tokyo. Anchored to the India floor the user chose
# (Rs 1 crore/day ~ USD 120k) and carried over rather than inventing a different
# standard per country. Tier cuts are the USD equivalents of the India bands.
#
# Median (not mean) turnover, so one block deal can't lift a dead stock over the bar.
# 🔴 WAS a single global 120_000 — India's Rs 1 crore gate applied to every market.
# Measured, it is a completely different filter in each: India 47th percentile, US 35th,
# JP 32nd, KR 23rd. One constant, four filters — a currency artefact, not a rule.
# adaptive_liquidity.scan_floor() splits the job: a STRUCTURAL floor ($10k/day — below
# which a listing is not transacted in ANY market) plus a POLICY floor only where a human
# chose one (India). The CAPITAL floor is deliberately NOT here: a scan does not know the
# consumer's capital, and baking one in is how a single portfolio size became four
# markets' definition of "liquid".
def _scan_floor(market: str = "") -> float:
    try:
        import adaptive_liquidity as _AL
        return _AL.scan_floor(market)
    except Exception:
        return 120_000.0        # legacy behaviour if the module is unavailable


SCAN_FLOOR_USD = 120_000                      # legacy constant; prefer _scan_floor(market)
SCAN_TIERS_USD = ((12_000_000, "T1_MEGA"),    # ~ >= Rs 100 cr/day
                  (3_000_000,  "T2_LARGE"),   # ~ Rs 25-100 cr
                  (600_000,    "T3_MID"),     # ~ Rs 5-25 cr
                  (0,          "T4_SMALL"))   # ~ Rs 1-5 cr


def measurable(df) -> bool:
    """True when the frame actually carries what turnover needs."""
    return (df is not None and hasattr(df, "columns")
            and "Close" in df.columns and "Volume" in df.columns)


def scan_gate(df, ticker: str, fx: Dict[str, float], market_hint: str = ""):
    """(median daily turnover USD, tier) — tier is None when below the floor.

    Currency comes from the ticker suffix, so this is safe on mixed-currency
    universes (the Europe scan) where a market key can't disambiguate.

    FAILS OPEN, deliberately: if the frame has no Volume column, or the currency
    has no FX rate, liquidity is UNMEASURABLE — which is not the same as
    "illiquid". Returning None there would silently empty an entire scan (a
    yfinance schema change dropping Volume would read as "no picks today" rather
    than a broken feed). Such rows are tagged "UNKNOWN" so they stay visible and
    can be filtered downstream on purpose rather than by accident.
    """
    if not measurable(df):
        return 0.0, "UNKNOWN"
    ccy = currency_for(ticker)
    base = SUBUNIT[ccy][0] if ccy in SUBUNIT else ccy
    if not fx.get(base):
        return 0.0, "UNKNOWN"
    tv = turnover_usd_for(df, ticker, fx)
    if tv < _scan_floor(market_hint):
        return tv, None
    for lo, name in SCAN_TIERS_USD:
        if tv >= lo:
            return tv, name
    return tv, "T4_SMALL"


def scan_fx() -> Dict[str, float]:
    """FX map for scan_gate: currency -> units per 1 USD. Call once per run."""
    need = sorted({c for c in CCY_BY_SUFFIX.values()} | {"USD"})
    need = [SUBUNIT[c][0] if c in SUBUNIT else c for c in need]
    fx = _fx_rates(need)
    return {k: v for k, v in fx.items() if v}


_SCAN_FX: Dict[str, float] = {}


def gate(df, ticker: str):
    """Process-cached liquidity gate for the market scans.

    (median daily turnover USD, tier); tier None => below the floor, skip the
    symbol. FX is fetched once per process, not per symbol. Every failure path
    yields "UNKNOWN" rather than None so a broken feed can never masquerade as
    "nothing qualified today".

    Usage in a scan's per-symbol loop:
        tv, tier = liquidity.gate(df, yf_ticker)
        if tier is None:
            continue
    """
    global _SCAN_FX
    if not _SCAN_FX:
        try:
            _SCAN_FX = scan_fx() or {"USD": 1.0}
        except Exception:
            _SCAN_FX = {"USD": 1.0}
    try:
        return scan_gate(df, ticker, _SCAN_FX)
    except Exception:
        return 0.0, "UNKNOWN"


FX_CACHE_PATH = Path(os.environ.get(
    "BHAV_CACHE", Path.home() / "Downloads" / "data" / "bhavcopy_cache")) / "fx_usd.json"
FX_STALE_DAYS = 7


def _fx_read_cache() -> Dict[str, float]:
    try:
        d = json.loads(FX_CACHE_PATH.read_text())
        age = (_dt.datetime.now() - _dt.datetime.fromisoformat(d["as_of"])).days
        if age > FX_STALE_DAYS:
            print(f"  fx: cache {age}d old (> {FX_STALE_DAYS}d) — refusing to use")
            return {}
        return {k: float(v) for k, v in d.get("rates", {}).items() if v}
    except Exception:
        return {}


def _fx_write_cache(rates: Dict[str, float]) -> None:
    try:
        FX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FX_CACHE_PATH.write_text(json.dumps(
            {"as_of": _dt.datetime.now().isoformat(),
             "rates": {k: v for k, v in rates.items() if v}}, indent=1))
    except Exception:
        pass


_UA = {"User-Agent": "Mozilla/5.0 (research)"}


def _fx_from_erapi(need: list) -> Dict[str, float]:
    """open.er-api.com — free, no key, ALL currencies in ONE call."""
    import json as _j
    import urllib.request as _u
    try:
        r = _u.Request("https://open.er-api.com/v6/latest/USD", headers=_UA)
        d = _j.load(_u.urlopen(r, timeout=20))
        rates = d.get("rates", {})
        return {c: float(rates[c]) for c in need if rates.get(c)}
    except Exception:
        return {}


def _fx_from_frankfurter(need: list) -> Dict[str, float]:
    """frankfurter.app — ECB reference rates, free, no key."""
    import json as _j
    import urllib.request as _u
    try:
        r = _u.Request(f"https://api.frankfurter.app/latest?from=USD&to={','.join(need)}",
                       headers=_UA)
        d = _j.load(_u.urlopen(r, timeout=20))
        return {c: float(v) for c, v in d.get("rates", {}).items() if v}
    except Exception:
        return {}


# FRED (Federal Reserve H.10) series, USD-quoted. Some are inverted (USD per unit).
_FRED_SERIES = {
    "JPY": ("DEXJPUS", False), "INR": ("DEXINUS", False), "KRW": ("DEXKOUS", False),
    "CHF": ("DEXSZUS", False), "CNY": ("DEXCHUS", False), "HKD": ("DEXHKUS", False),
    "TWD": ("DEXTAUS", False), "SGD": ("DEXSIUS", False), "BRL": ("DEXBZUS", False),
    "MXN": ("DEXMXUS", False), "ZAR": ("DEXSAUS", False), "CAD": ("DEXCAUS", False),
    "SEK": ("DEXSDUS", False), "NOK": ("DEXNOUS", False), "DKK": ("DEXDNUS", False),
    "EUR": ("DEXUSEU", True), "GBP": ("DEXUSUK", True), "AUD": ("DEXUSAL", True),
    "NZD": ("DEXUSNZ", True),
}


def _fred_key() -> str:
    k = os.environ.get("FRED_API_KEY", "")
    if k:
        return k
    for p in (Path.home() / ".env.local", Path(__file__).parent / ".env"):
        try:
            for line in p.read_text().splitlines():
                if line.startswith("FRED_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


def _fx_from_fred(need: list) -> Dict[str, float]:
    """FRED — official Fed H.10. Authoritative but a few business days lagged."""
    import json as _j
    import urllib.request as _u
    key = _fred_key()
    if not key:
        return {}
    out = {}
    for c in need:
        sid = _FRED_SERIES.get(c)
        if not sid:
            continue
        series, inverted = sid
        try:
            url = ("https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={series}&api_key={key}&file_type=json"
                   "&sort_order=desc&limit=5")
            d = _j.load(_u.urlopen(url, timeout=20))
            obs = [o for o in d.get("observations", []) if o.get("value") not in (".", "", None)]
            if not obs:
                continue
            v = float(obs[0]["value"])
            out[c] = (1.0 / v) if inverted else v
        except Exception:
            continue
    return out


def _fx_rates(currencies) -> Dict[str, float]:
    """USD value of 1 unit-of-USD in each currency. Live, with a REAL disk cache.

    The docstring used to promise "cache fallback" and there was none: on a failed
    fetch every currency came back None, scan_fx() dropped them, and scan_gate then
    returned UNKNOWN for every non-USD ticker — silently DISABLING the liquidity
    gate for India/Japan/Korea/Europe while leaving US intact. That is exactly what
    happened during the 2026-07-15 sample run, when a saturated yfinance returned
    "23 Failed downloads: ['SEK=X','INR=X',...]": the markets most in need of the
    gate quietly stopped being gated.

    Now the last good rates are persisted and reused when a fetch fails. FX moves
    ~1%/day against tier bands that are 5-10x wide, so a day-old rate is
    immaterial to a liquidity decision — while a missing rate removes the gate
    entirely. Refuses a cache older than FX_STALE_DAYS rather than pretend.
    """
    need = sorted(set(currencies) - {"USD"})
    fx: Dict[str, float] = {"USD": 1.0}
    used = []

    # Source order is deliberate. yfinance is LAST despite being the most "live":
    # it needs one download PER PAIR (23 calls), is the component already tripping
    # Yahoo's rate limiter, and returned nothing at all during the 2026-07-15 run
    # ("23 Failed downloads: ['SEK=X','INR=X',...]"). open.er-api returns EVERY
    # currency in ONE keyless call, so it is both more reliable and lighter — and
    # using it first takes pressure off the same rate limiter the scans depend on.
    # Cross-checked 2026-07-15: INR 96.24 (er-api) / 96.2 (frankfurter) / 96.3
    # (yfinance) / 95.33 (FRED, a few days lagged) — all inside the ~1% that a
    # 5-10x-wide tier band cannot notice.
    for name, fn in (("er-api", _fx_from_erapi),
                     ("frankfurter", _fx_from_frankfurter),
                     ("fred", _fx_from_fred)):
        missing = [c for c in need if not fx.get(c)]
        if not missing:
            break
        got = fn(missing)
        if got:
            fx.update(got)
            used.append(f"{name}:{len(got)}")

    missing = [c for c in need if not fx.get(c)]
    if missing:                                    # last resort: the flaky one
        try:
            import yfinance as yf
            d = yf.download([f"{c}=X" for c in missing], period="5d",
                            progress=False)["Close"]
            n = 0
            for c in missing:
                try:
                    v = float(d[f"{c}=X"].dropna().iloc[-1])
                    if v > 0:
                        fx[c] = v
                        n += 1
                except Exception:
                    continue
            if n:
                used.append(f"yfinance:{n}")
        except Exception:
            pass

    live = {k: v for k, v in fx.items() if v and k != "USD"}
    if live:
        _fx_write_cache({**_fx_read_cache(), **live})
    if used:
        print(f"  fx: {len(live)}/{len(need)} rates from {', '.join(used)}")

    missing = [c for c in need if not fx.get(c)]
    if missing:
        cached = _fx_read_cache()
        filled = [c for c in missing if cached.get(c)]
        for c in filled:
            fx[c] = cached[c]
        if filled:
            print(f"  fx: {len(filled)} rate(s) served from cache "
                  f"({', '.join(filled[:6])}{'…' if len(filled) > 6 else ''})")
        still = [c for c in missing if not fx.get(c)]
        if still:
            # Loud: these markets lose their gate this run.
            print(f"  ⚠️  fx: NO rate for {', '.join(still[:8])} — the liquidity gate "
                  f"is INACTIVE for those markets this run (tier=UNKNOWN)")
    return fx


def build_index(verbose: bool = True) -> pd.DataFrame:
    """Compute per-symbol 20-day median turnover (USD) across all market seeds."""
    import screener_kit as kit
    fx = _fx_rates(CCY.values())
    rows = []
    for m in kit.MARKETS:
        rate = fx.get(CCY.get(m))
        if not rate:
            continue
        data = kit.load(m)
        unit = UNIT.get(m, 1.0)
        for s, df in data.items():
            if df is None or len(df) < 20 or "Volume" not in df.columns:
                continue
            t = float((df["Close"] * df["Volume"]).tail(20).median())
            if t > 0:
                rows.append({"Symbol": s, "Market": m,
                             "turnover_usd": (t / unit) / rate,
                             "ltp": float(df["Close"].iloc[-1])})
        if verbose:
            print(f"  {m}: indexed {sum(1 for r in rows if r['Market']==m)} stocks")
    idx = pd.DataFrame(rows)
    if not idx.empty:
        idx.to_parquet(INDEX_PATH, compression="zstd", index=False)
    if verbose:
        print(f"  liquidity index: {len(idx)} symbols → {INDEX_PATH.name}")
    return idx


def _load_index() -> pd.DataFrame:
    return pd.read_parquet(INDEX_PATH) if INDEX_PATH.exists() else pd.DataFrame()


# liquidity tiers by USD median daily turnover (global defaults)
HIGH = 10_000_000      # ≥ $10M/day  → High
MED = 1_000_000        # $1M–$10M/day → Medium  (< $1M → Low)

# Per-market overrides (high, medium) — smaller/thinner markets use lower bars so
# "High/Medium/Low" is meaningful *within* each market. Tune freely.
MARKET_TIERS = {
    "US": (20_000_000, 2_000_000), "CN": (20_000_000, 2_000_000),
    "JP": (10_000_000, 1_000_000), "EU": (10_000_000, 1_000_000),
    "HK": (5_000_000, 500_000),    "TW": (5_000_000, 500_000),
    "KR": (5_000_000, 500_000),    "UK": (5_000_000, 500_000),
    "DE": (5_000_000, 500_000),    "CA": (3_000_000, 300_000),
    "AU": (3_000_000, 300_000),    "IN": (5_000_000, 500_000),
    "BR": (3_000_000, 300_000),    "SA": (3_000_000, 300_000),
    "CH": (3_000_000, 300_000),    "SG": (2_000_000, 200_000),
    "ZA": (2_000_000, 200_000),    "SE": (2_000_000, 200_000),
    "FI": (1_000_000, 100_000),    "DK": (1_000_000, 100_000),
}


def tier(turnover_usd: Optional[float], market: Optional[str] = None) -> str:
    if turnover_usd is None:
        return "Unknown"
    hi, med = MARKET_TIERS.get(market, (HIGH, MED))
    if turnover_usd >= hi:
        return "High"
    if turnover_usd >= med:
        return "Medium"
    return "Low"


_CACHE_MAP = {}


def _turnover_map() -> Dict[str, float]:
    global _CACHE_MAP
    if not _CACHE_MAP:
        idx = _load_index()
        if not idx.empty:
            _CACHE_MAP = dict(zip(idx["Symbol"], idx["turnover_usd"]))
    return _CACHE_MAP


def annotate(df: pd.DataFrame, symbol_col: str = "Symbol") -> pd.DataFrame:
    """Add Turnover_USD and Liquidity (High/Medium/Low) columns to a result frame."""
    if df is None or df.empty or symbol_col not in df.columns:
        return df
    tmap = _turnover_map()
    df = df.copy()
    df["Turnover_USD"] = df[symbol_col].map(tmap).round(0)
    if "Market" in df.columns:
        df["Liquidity"] = [tier(t, m) for t, m in zip(df["Turnover_USD"], df["Market"])]
    else:
        df["Liquidity"] = df["Turnover_USD"].map(tier)
    return df


def turnover(symbol: str) -> Optional[float]:
    """USD median daily turnover for one symbol (from the cached index)."""
    idx = _load_index()
    hit = idx[idx["Symbol"] == symbol]
    return float(hit.iloc[0]["turnover_usd"]) if not hit.empty else None


def liquid_symbols(market: Optional[str] = None, min_usd: float = 1_000_000,
                   top: Optional[int] = None) -> List[str]:
    """Symbols trading at least `min_usd`/day, optionally limited to a market and
    the top-N most liquid. This is the fast pre-filter for screens."""
    idx = _load_index()
    if idx.empty:
        return []
    if market:
        idx = idx[idx["Market"] == market]
    idx = idx[idx["turnover_usd"] >= min_usd].sort_values("turnover_usd", ascending=False)
    if top:
        idx = idx.head(top)
    return idx["Symbol"].tolist()


if __name__ == "__main__":
    import sys
    if "--build" in sys.argv:
        build_index()
    idx = _load_index()
    if not idx.empty:
        print(f"\nindex: {len(idx)} symbols")
        for m in idx["Market"].unique():
            sub = idx[idx["Market"] == m]
            liq = (sub["turnover_usd"] >= 1e6).sum()
            print(f"  {m}: {len(sub):>5} total, {liq:>4} liquid (≥$1M/day)")
