#!/usr/bin/env python3
# bundle_validation.py
# ====================
# Validate the model-portfolio bundles against REAL funds and indices (user,
# 2026-07-23): for each bundle, find the closest public benchmark, compare
# constituents and weights, and say plainly whether the bundle is a genuine
# active tilt or a closet index fund.
#
# WHY THIS IS THE VALIDATION STRATEGY:
#   * If a bundle largely replicates XLF/Nifty Bank at similar weights, it
#     adds nothing over just buying that fund — flag it, don't celebrate it.
#   * If overlap is LOW, the bundle is a differentiated satellite — which is
#     what screen-driven selection SHOULD produce — and the benchmark tells
#     you what it's differentiated FROM.
#   * Constituent comparison also audits our sector labels: an "Energy"
#     bundle whose members appear in no energy index is either small-cap
#     (fine, say so) or mislabelled (fix it).
#
# BENCHMARK SOURCES (public, no auth — MSCI MCP was tried first but the
# account has no index-data entitlement):
#   US  SPDR sector ETF daily holdings XLSX (ssga.com) — WITH weights →
#       overlap + active share + concentration comparison.
#   IN  NSE index constituent CSVs (niftyindices.com) — membership only →
#       overlap + Nifty-500 membership (large/mid vs small-cap tilt).
#   JP/KR/EU — no free constituent feed wired yet; reported as such.
#
# Downloads are cached in data/benchmark_holdings/ for 7 days.

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "data" / "benchmark_holdings"
OUT_MD = HERE / "reports" / "bundle_validation.md"
MAX_AGE_S = 7 * 86400
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

SPDR = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{t}.xlsx"
NSE = "https://www.niftyindices.com/IndexConstituent/{f}"

# dominant-sector → benchmark mapping
US_ETF = {"Energy": ("XLE", "Energy Select SPDR"),
          "Financial Services": ("XLF", "Financial Select SPDR"),
          "Healthcare": ("XLV", "Health Care Select SPDR"),
          "Industrials": ("XLI", "Industrial Select SPDR"),
          "Technology": ("XLK", "Technology Select SPDR"),
          "Consumer Cyclical": ("XLY", "Consumer Discretionary SPDR"),
          "Consumer Defensive": ("XLP", "Consumer Staples SPDR"),
          "Basic Materials": ("XLB", "Materials Select SPDR"),
          "Real Estate": ("XLRE", "Real Estate SPDR"),
          "Utilities": ("XLU", "Utilities SPDR"),
          "Communication Services": ("XLC", "Communication SPDR")}
IN_IDX = {"Financial Services": ("ind_niftyfinancelist.csv", "Nifty Financial Services"),
          "Banks": ("ind_niftybanklist.csv", "Nifty Bank"),
          "Energy": ("ind_niftyenergylist.csv", "Nifty Energy"),
          "Consumer Cyclical": ("ind_niftyconsumerdurableslist.csv", "Nifty Consumer Durables"),
          "Healthcare": ("ind_niftypharmalist.csv", "Nifty Pharma"),
          "Technology": ("ind_niftyitlist.csv", "Nifty IT"),
          "Consumer Defensive": ("ind_niftyfmcglist.csv", "Nifty FMCG"),
          "Basic Materials": ("ind_niftymetallist.csv", "Nifty Metal"),
          "Industrials": ("ind_niftyinfralist.csv", "Nifty Infrastructure")}
IN_BROAD = ("ind_nifty500list.csv", "Nifty 500")


def _fetch(url: str, dest: Path) -> bool:
    if dest.exists() and time.time() - dest.stat().st_mtime < MAX_AGE_S:
        return True
    CACHE.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", UA, url,
                        "-o", str(dest)], capture_output=True)
    ok = r.returncode == 0 and dest.exists() and dest.stat().st_size > 500
    if ok and dest.suffix == ".csv":
        ok = b"<html" not in dest.read_bytes()[:200].lower()
    return ok


def spdr_holdings(ticker: str) -> pd.DataFrame:
    dest = CACHE / f"{ticker}.xlsx"
    if not _fetch(SPDR.format(t=ticker.lower()), dest):
        return pd.DataFrame()
    df = pd.read_excel(dest, skiprows=4)
    df = df.dropna(subset=["Ticker"])
    df = df[pd.to_numeric(df.Weight, errors="coerce").notna()]
    df["Weight"] = df.Weight.astype(float) / 100.0
    return df[["Ticker", "Name", "Weight"]]


def nse_members(fname: str) -> set:
    dest = CACHE / fname
    if not _fetch(NSE.format(f=fname), dest):
        return set()
    try:
        return set(pd.read_csv(dest)["Symbol"].astype(str).str.upper())
    except Exception:
        return set()


def hhi(weights) -> float:
    w = np.asarray(list(weights), dtype=float)
    return float((w ** 2).sum())


def validate(bundles: list) -> str:
    lines = ["# Bundle validation vs public benchmarks", "",
             "Per bundle: closest real index/fund, constituent overlap, weight "
             "style. **Low overlap = differentiated satellite (the point of "
             "screen-driven selection); high overlap + similar weights = closet "
             "index — just buy the fund.** MSCI MCP unentitled; sources are "
             "SPDR daily holdings (US, with weights) and NSE constituent lists "
             "(India, membership).", ""]
    n500 = nse_members(IN_BROAD[0])
    for b in bundles:
        mkt = b["market"]
        members = b["members"]
        syms = [m["symbol"].upper() for m in members]
        ours = {m["symbol"].upper(): m["weight"] for m in members}
        from collections import Counter
        secs = Counter(m.get("sector") for m in members
                       if m.get("sector") not in (None, "", "Unclassified"))
        dom = secs.most_common(1)[0][0] if secs else None
        lines.append(f"## {b['name']}  ({len(members)} names, formed {b['formed']})")
        if mkt == "US" and dom in US_ETF:
            etf, ename = US_ETF[dom]
            hold = spdr_holdings(etf)
            if hold.empty:
                lines.append(f"- benchmark {ename} ({etf}): download failed\n")
                continue
            bw = dict(zip(hold.Ticker.str.upper(), hold.Weight))
            common = [s for s in syms if s in bw]
            active_share = 1 - sum(min(ours[s], bw.get(s, 0)) for s in syms)
            lines += [
                f"- benchmark: **{ename} ({etf})** — {len(hold)} holdings, "
                f"top weight {hold.Weight.max()*100:.1f}%, HHI {hhi(hold.Weight):.3f}",
                f"- constituent overlap: **{len(common)}/{len(syms)}** of our "
                f"names are in the ETF"
                + (f" ({', '.join(common)})" if common else ""),
                f"- active share vs {etf}: **{active_share*100:.0f}%** "
                f"(100% = nothing in common at weight level)",
                f"- weight style: our HHI {hhi(ours.values()):.3f} / top "
                f"{max(ours.values())*100:.0f}% (inverse-vol, capped 25%) vs "
                f"ETF cap-weight top {hold.Weight.max()*100:.1f}%",
                _verdict(len(common), len(syms), active_share), ""]
        elif mkt == "IN":
            bench = IN_IDX.get(dom)
            # Banks industries map to Financial Services sector; try both
            memb = nse_members(bench[0]) if bench else set()
            in_bench = [s for s in syms if s in memb]
            in_500 = [s for s in syms if s in n500]
            lines += [
                f"- benchmark: **{bench[1] if bench else 'none mapped'}** "
                f"(membership only — NSE publishes no weights in these lists)",
                f"- constituent overlap: **{len(in_bench)}/{len(syms)}**"
                + (f" ({', '.join(in_bench)})" if in_bench else ""),
                f"- Nifty 500 membership: **{len(in_500)}/{len(syms)}** — "
                f"{'large/mid-cap oriented' if len(in_500) > len(syms)/2 else 'a SMALL-CAP tilt no index fund carries'}",
                _verdict(len(in_bench), len(syms), None), ""]
        else:
            lines += [f"- no free constituent feed wired for {mkt} yet "
                      f"(JP: JPX TOPIX lists, KR: KRX, EU: STOXX — all "
                      f"factsheet-only top-10s); skipped honestly.", ""]
    return "\n".join(lines)


def _verdict(overlap: int, n: int, active_share) -> str:
    frac = overlap / n if n else 0
    if active_share is not None and active_share < 0.6:
        return ("- **verdict: CLOSET INDEX** — high weight-level similarity; "
                "buying the ETF is cheaper than running this bundle")
    if frac >= 0.7:
        return ("- **verdict: index-like membership** — differentiation comes "
                "only from weights; compare costs vs the fund")
    if frac >= 0.3:
        return ("- **verdict: blended** — part index names, part satellite; "
                "the off-index names are where the screen adds anything")
    return ("- **verdict: differentiated satellite** — the screens picked "
            "names the index funds don't carry; complements (not replaces) "
            "an index holding")


def main() -> int:
    import json
    store = json.loads((HERE / "cache_seed" / "portfolio_bundles.json").read_text())
    text = validate(store["bundles"])
    OUT_MD.write_text(text)
    print(text)
    print(f"\nwrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
