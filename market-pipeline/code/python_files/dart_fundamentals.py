# dart_fundamentals.py
# ====================
# Korean company fundamentals from DART (금융감독원 전자공시), the FSS's official
# electronic-disclosure system — the primary source Korean filings actually land in.
#
# WHY THIS EXISTS
# ───────────────
# full_korea_market_scan.py computed Piotroski from yfinance. On KRX that is a
# poor source: yfinance's Korean statement coverage is thin and inconsistent, so
# Korea's Piotroski block degraded silently rather than failing loudly. DART is
# the regulator's own filing database, so coverage is the filing universe itself
# (3,977 listed corp codes) rather than whatever a US-centric aggregator happens
# to carry.
#
# TWO PROPERTIES THAT MATTER FOR COST
# ───────────────────────────────────
#   * fnlttSinglAcntAll returns the CURRENT and PRIOR term in ONE response
#     (thstrm_amount / frmtrm_amount). Piotroski needs exactly two years, so one
#     HTTP call per company covers it — not two.
#   * Accounts carry IFRS `account_id` tags (ifrs-full_Assets, …). Matching on
#     those instead of the Korean `account_nm` avoids the name-matching fragility
#     that makes the yfinance path brittle in the first place.
#
# CACHING
# Statements change quarterly at most, so results are cached on disk and reused
# for CACHE_DAYS. A nightly scan must not re-pull 2,500 filings that cannot have
# changed; DART's daily request quota is finite and shared with every other user
# of the key.
#
#   from dart_fundamentals import piotroski_inputs
#   d = piotroski_inputs("005930")     # bare 6-digit KRX code
#
# Returns None when the company is not in DART or has not filed — the caller
# must treat that as "unknown", NOT as "failed the screen".

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, Optional

import env_loader as _env

# Cache root. The fallback must NOT hardcode ~/Downloads: macOS TCC denies
# launchd all access there, so a scheduled run would fail with PermissionError
# at first write — which is exactly how the nightly US scan died on 2026-07-20,
# and how this line was originally written hours after that was diagnosed.
# $MARKET_CACHE is the same variable data_registry reads, so the fallback lands
# in the same place rather than somewhere unreachable.
try:
    import data_registry as R
    _CACHE_ROOT = R.MARKET_CACHE / "dart"
except ImportError as e:
    # Narrow: only a genuinely absent module falls back. A registry that raises
    # for any OTHER reason (bad env var, unreadable path) must surface — the
    # broad `except Exception` here would have swallowed that and quietly used
    # a different cache directory, so Korea would look empty with no error.
    print(f"dart_fundamentals: data_registry unavailable ({e}) — "
          "falling back to $MARKET_CACHE", file=sys.stderr)
    _CACHE_ROOT = Path(
        os.environ.get("MARKET_CACHE", Path.home() / "market_cache")) / "dart"

_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
_CORP_MAP = _CACHE_ROOT / "corp_map.json"
_FIN_DIR = _CACHE_ROOT / "fin"
_FIN_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://opendart.fss.or.kr/api"
CACHE_DAYS = 30          # statements are quarterly at most
CORP_MAP_DAYS = 14       # new listings appear occasionally
TIMEOUT = 60
SLEEP = 0.05             # DART is generous, but do not hammer it

# Annual report. 11011 = 사업보고서 (annual); the quarterly codes are 11012/11013/11014.
REPRT_ANNUAL = "11011"

# IFRS tags → the fields Piotroski needs. Verified present on a real filing
# 2026-07-21. Tuples are fallbacks tried in order: consolidated filers use the
# first, some smaller filers only report the broader aggregate.
TAGS = {
    "total_assets":      ("ifrs-full_Assets",),
    "current_assets":    ("ifrs-full_CurrentAssets",),
    "current_liabs":     ("ifrs-full_CurrentLiabilities",),
    "noncurrent_liabs":  ("ifrs-full_NoncurrentLiabilities",),
    "total_liabs":       ("ifrs-full_Liabilities",),
    "equity":            ("ifrs-full_Equity",),
    "net_income":        ("ifrs-full_ProfitLoss",),
    "revenue":           ("ifrs-full_Revenue",),
    "gross_profit":      ("ifrs-full_GrossProfit",),
    "operating_cf":      ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
}


def _key() -> str:
    k = _env.get("DART_KEY")
    if not k:
        raise KeyError("DART_KEY not set — add it to .env")
    return k


def _get(url: str) -> bytes:
    return urllib.request.urlopen(url, timeout=TIMEOUT).read()


def _fresh(p: Path, days: float) -> bool:
    return p.exists() and (time.time() - p.stat().st_mtime) < days * 86400


# ── stock code → corp code ────────────────────────────────────────────────────
def corp_map(force: bool = False) -> Dict[str, str]:
    """{'005930': '00126380', …} for every DART corp with a listed stock code.

    DART keys everything on its own 8-digit corp_code, never the ticker, so this
    mapping is mandatory. It ships as a ~3.5 MB zipped XML of ALL 118k registered
    entities; only the ~4k with a stock_code are listed companies.
    """
    if not force and _fresh(_CORP_MAP, CORP_MAP_DAYS):
        try:
            return json.loads(_CORP_MAP.read_text())
        except Exception:
            pass
    url = f"{BASE}/corpCode.xml?" + urllib.parse.urlencode({"crtfc_key": _key()})
    z = zipfile.ZipFile(io.BytesIO(_get(url)))
    root = ET.fromstring(z.read(z.namelist()[0]))
    out = {}
    for x in root.findall("list"):
        sc = (x.findtext("stock_code") or "").strip()
        if sc:
            out[sc] = x.findtext("corp_code")
    _CORP_MAP.write_text(json.dumps(out))
    return out


# ── raw statements ────────────────────────────────────────────────────────────
def _statements(corp_code: str, year: str, fs_div: str = "CFS") -> Optional[list]:
    """All accounts for one company-year, cached.

    fs_div CFS = consolidated, OFS = separate. Consolidated is the right default
    for a group; companies that file only separate statements are retried as OFS
    by the caller rather than silently reported as having no data.
    """
    cache = _FIN_DIR / f"{corp_code}_{year}_{fs_div}.json"
    if _fresh(cache, CACHE_DAYS):
        try:
            return json.loads(cache.read_text()).get("list")
        except Exception:
            pass
    url = f"{BASE}/fnlttSinglAcntAll.json?" + urllib.parse.urlencode({
        "crtfc_key": _key(), "corp_code": corp_code, "bsns_year": year,
        "reprt_code": REPRT_ANNUAL, "fs_div": fs_div})
    try:
        d = json.loads(_get(url))
    except Exception:
        return None
    time.sleep(SLEEP)
    if d.get("status") != "000":
        # 013 = no data for that year/company. Cache the miss too: without this a
        # non-filer is re-requested on every nightly run forever.
        cache.write_text(json.dumps({"status": d.get("status"), "list": []}))
        return None
    cache.write_text(json.dumps({"status": "000", "list": d.get("list", [])}))
    return d.get("list", [])


def _amount(rows: list, tags: tuple, which: str) -> Optional[float]:
    """which = 'thstrm_amount' (current year) or 'frmtrm_amount' (prior year)."""
    for tag in tags:
        for r in rows:
            if r.get("account_id") == tag:
                v = (r.get(which) or "").replace(",", "").strip()
                if v in ("", "-"):
                    continue
                try:
                    return float(v)
                except ValueError:
                    continue
    return None


# ── the accessor the scan uses ────────────────────────────────────────────────
def piotroski_inputs(stock_code: str, year: Optional[str] = None) -> Optional[dict]:
    """Two years of Piotroski inputs for a KRX code, or None if DART has nothing.

    Keys are suffixed _0 (most recent) and _1 (prior) to mirror the col=0/col=1
    convention the existing yfinance path uses, so the F-score arithmetic does
    not have to change.
    """
    code = str(stock_code).strip().zfill(6)
    cc = corp_map().get(code)
    if not cc:
        return None

    if year is None:
        # Annual reports land ~90 days after year-end, so early in a calendar
        # year the most recent FILED annual report is still the prior year.
        # Try the current year and walk back rather than assuming.
        import datetime as _dt
        years = [str(_dt.date.today().year - d) for d in (0, 1, 2)]
    else:
        years = [str(year)]

    rows = None
    used_year = used_div = None
    for y in years:
        for div in ("CFS", "OFS"):
            r = _statements(cc, y, div)
            if r:
                rows, used_year, used_div = r, y, div
                break
        if rows:
            break
    if not rows:
        return None

    out = {"code": code, "corp_code": cc, "year": used_year, "fs_div": used_div,
           "source": "dart"}
    for field, tags in TAGS.items():
        out[f"{field}_0"] = _amount(rows, tags, "thstrm_amount")
        out[f"{field}_1"] = _amount(rows, tags, "frmtrm_amount")
    return out


def f_score(d: dict) -> Optional[dict]:
    """Piotroski F-score from DART inputs. Mirrors the yfinance path's 9 tests.

    F7 (share issuance) is NOT computable: DART's statement endpoint carries no
    share-count tag. It is scored 1 — the same default the yfinance path uses
    when share data is absent — and flagged in `caveats` so a 9/9 built on an
    assumed test is not mistaken for a fully evidenced one.
    """
    if not d:
        return None
    g = d.get
    a0, a1 = g("total_assets_0"), g("total_assets_1")
    ni0, ni1 = g("net_income_0"), g("net_income_1")
    ocf0 = g("operating_cf_0")
    if not (a0 and a1):
        return None

    roa0 = (ni0 / a0) if (ni0 is not None and a0) else None
    roa1 = (ni1 / a1) if (ni1 is not None and a1) else None

    f1 = 1 if (roa0 is not None and roa0 > 0) else 0
    f2 = 1 if (ocf0 is not None and ocf0 > 0) else 0
    f3 = 1 if (roa0 is not None and roa1 is not None and roa0 > roa1) else 0
    f4 = 1 if (ocf0 is not None and roa0 is not None and (ocf0 / a0) > roa0) else 0

    ltd0, ltd1 = g("noncurrent_liabs_0") or 0, g("noncurrent_liabs_1") or 0
    f5 = 1 if ((ltd0 / a0) < (ltd1 / a1)) else 0

    ca0, cl0 = g("current_assets_0"), g("current_liabs_0")
    ca1, cl1 = g("current_assets_1"), g("current_liabs_1")
    f6 = 1 if (ca0 and cl0 and ca1 and cl1 and (ca0 / cl0) > (ca1 / cl1)) else 0

    f7 = 1                       # not computable — see docstring
    rev0, gp0 = g("revenue_0"), g("gross_profit_0")
    rev1, gp1 = g("revenue_1"), g("gross_profit_1")
    f8 = 1 if (gp0 and rev0 and gp1 and rev1 and (gp0 / rev0) > (gp1 / rev1)) else 0
    f9 = 1 if (rev0 and rev1 and (rev0 / a0) > (rev1 / a1)) else 0

    return {"f_score": f1+f2+f3+f4+f5+f6+f7+f8+f9,
            "components": {"f1": f1, "f2": f2, "f3": f3, "f4": f4, "f5": f5,
                           "f6": f6, "f7": f7, "f8": f8, "f9": f9},
            "year": d.get("year"), "fs_div": d.get("fs_div"), "source": "dart",
            "caveats": ["F7 (share issuance) not in DART statements — scored 1"]}


if __name__ == "__main__":
    import sys
    for c in (sys.argv[1:] or ["005930", "000660", "035720"]):
        d = piotroski_inputs(c)
        s = f_score(d) if d else None
        if s:
            print(f"  {c}  F={s['f_score']}/9  year={s['year']} {s['fs_div']}  {s['components']}")
        else:
            print(f"  {c}  no DART data")
