#!/usr/bin/env python3
# universe_sources.py
# ===================
# Full tradable-universe providers per market, preferring OFFICIAL / government /
# exchange sources over scraping. Each provider returns yfinance-style tickers.
#
#   US — SEC EDGAR company_tickers.json          (US government, ~10k filers)
#   IN — NSE+BSE bhavcopy symbols                (exchange official)
#   JP — JPX listed-issue master (.T)            (exchange official, ~3.8k)
#   KR — KRX KIND KOSPI+KOSDAQ (.KS/.KQ)         (exchange official, ~2.6k)
#   SG — SGX securities API (.SI)                (exchange official, ~620)
#   CN — Eastmoney A-share list (.SS/.SZ)        (full A-share board, ~5.5k)
#   EU — STOXX-large-cap curated (multi-venue)   (index constituents)
#
# Government/official endpoints are documented inline so they can be audited.

from __future__ import annotations

import warnings
from typing import List

import requests

warnings.filterwarnings("ignore")
_UA = {"User-Agent": "Mozilla/5.0 (market-research)"}
_SEC_UA = {"User-Agent": "market-research umashankartd1991@gmail.com"}  # SEC requires contact


def us_sec() -> List[str]:
    """US: SEC EDGAR official ticker registry (government source)."""
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers=_SEC_UA, timeout=30)
    r.raise_for_status()
    return sorted({v["ticker"].upper().replace(".", "-") for v in r.json().values()
                   if v.get("ticker")})


def sg_sgx() -> List[str]:
    """SG: SGX official securities API → stocks + reits + business trusts."""
    r = requests.get("https://api.sgx.com/securities/v1.1?excludetypes=bonds&params=nc%2Ctype",
                     headers=_UA, timeout=30)
    r.raise_for_status()
    keep = {"stocks", "reits", "businesstrusts"}
    return sorted({f"{d['nc']}.SI" for d in r.json()["data"]["prices"]
                   if d.get("nc") and d.get("type") in keep})


def cn_eastmoney() -> List[str]:
    """CN: full A-share universe via Eastmoney push2 list API.
    fs boards: m:1 t:2/t:23 (SSE A/STAR), m:0 t:6/t:80 (SZSE A/ChiNext)."""
    out, pn, total = [], 1, None
    fs = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80"
    hosts = ["https://push2.eastmoney.com", "https://82.push2.eastmoney.com",
             "http://80.push2.eastmoney.com", "https://push2delay.eastmoney.com"]
    while True:
        data = None
        for host in hosts:
            try:
                r = requests.get(f"{host}/api/qt/clist/get",
                                 params={"pn": pn, "pz": 200, "fs": fs, "fields": "f12,f13"},
                                 headers=_UA, timeout=30)
                data = r.json().get("data") or {}
                break
            except Exception:
                continue
        if not data:
            break
        total = total or data.get("total")
        diff = data.get("diff") or []
        if isinstance(diff, dict):               # some hosts key diff by index
            diff = list(diff.values())
        if not diff:
            break
        for d in diff:
            code, mkt = d.get("f12"), d.get("f13")     # f13: 1=Shanghai, 0=Shenzhen
            if code:
                out.append(f"{code}.SS" if mkt == 1 else f"{code}.SZ")
        if total and len(out) >= total:
            break
        pn += 1
    return sorted(set(out))


def jp_jpx() -> List[str]:
    from full_japan_market_scan import fetch_tse_universe_jpx, fetch_tse_universe_kabupy
    uni = []
    try:
        uni = fetch_tse_universe_jpx()
    except Exception:
        uni = []
    if not uni:
        uni = fetch_tse_universe_kabupy()
    return sorted({u.get("yf_ticker") or f"{u['code']}.T" for u in uni
                   if u.get("code") or u.get("yf_ticker")})


def kr_krx() -> List[str]:
    from full_korea_market_scan import build_krx_universe
    return sorted({f"{u['code']}{u.get('yf_suffix', '.KS')}"
                   for u in build_krx_universe() if u.get("code")})


def in_bhavcopy() -> List[str]:
    """IN: symbols present in the bhavcopy assembled/cleaned cache (exchange EOD)."""
    try:
        import bhavcopy_store as s
        syms = s.symbols()
        if syms:
            return sorted(syms)
    except Exception:
        pass
    from bhavcopy_history import fetch_history
    return sorted(fetch_history(verbose=False).keys())


# EU is fragmented across LSE/Euronext/Xetra/SIX with no single free official
# all-share feed; ship a broad multi-venue large/mid-cap set (STOXX-50 + DAX +
# CAC + AEX + FTSE majors). Expand by appending more constituents here.
def eu_curated() -> List[str]:
    from full_european_market_scan import EURO_STOXX_50_META
    extra = [
        # FTSE (London .L)
        "HSBA.L","BP.L","SHEL.L","AZN.L","ULVR.L","GSK.L","RIO.L","GLEN.L","BATS.L",
        "DGE.L","LSEG.L","REL.L","NG.L","BARC.L","LLOY.L","NWG.L","VOD.L","TSCO.L",
        "PRU.L","AAL.L","RR.L","BA.L","IMB.L","CPG.L","NXT.L","STAN.L","AV.L",
        # DAX (Xetra .DE) beyond stoxx50
        "SAP.DE","SIE.DE","DTE.DE","MBG.DE","VOW3.DE","BMW.DE","BAS.DE","BAYN.DE",
        "RWE.DE","EOAN.DE","DB1.DE","DBK.DE","ADS.DE","MUV2.DE","IFX.DE","HEN3.DE",
        # CAC (Paris .PA) beyond stoxx50
        "MC.PA","OR.PA","RMS.PA","TTE.PA","SAN.PA","BNP.PA","AIR.PA","SU.PA","CS.PA",
        "EL.PA","DG.PA","BN.PA","KER.PA","SAF.PA","STLAP.PA","ENGI.PA","VIE.PA",
        # AEX (Amsterdam .AS) / SIX (.SW)
        "ASML.AS","PRX.AS","INGA.AS","AD.AS","PHIA.AS","WKL.AS","HEIA.AS",
        "NESN.SW","ROG.SW","NOVN.SW","UBSG.SW","ZURN.SW","ABBN.SW","CFR.SW",
    ]
    return sorted(set(EURO_STOXX_50_META.keys()) | set(extra))


PROVIDERS = {
    "US": us_sec, "IN": in_bhavcopy, "JP": jp_jpx, "KR": kr_krx,
    "SG": sg_sgx, "CN": cn_eastmoney, "EU": eu_curated,
}


def get_universe(market: str) -> List[str]:
    return PROVIDERS[market.upper()]()


if __name__ == "__main__":
    import sys
    mkts = [m.upper() for m in sys.argv[1:]] or list(PROVIDERS)
    for m in mkts:
        try:
            u = get_universe(m)
            print(f"  {m}: {len(u):>6} tickers   e.g. {u[:4]}")
        except Exception as e:
            print(f"  {m}: ERROR {str(e)[:70]}")
