#!/usr/bin/env python3
"""
korea_common_preferred_correlation.py
=======================================
Do a Korean company's common and preferred shares move together?

KOSPI (rarely KOSDAQ) frequently lists a Korean company's preferred share
class as a SEPARATE ticker alongside its common share -- e.g. Samsung
Electronics common (005930.KS) and Samsung Electronics preferred
(005935.KS). Unlike NSE/BSE (same company, same ticker string, two
different exchange suffixes) or unlike a true cross-exchange dual listing,
this is two DIFFERENT numeric codes on the SAME exchange, distinguished
only by the company name carrying a trailing preferred-share marker.

Preferred-share names always end with a suffix built from these tokens:
an optional digit (2nd/3rd/... preferred issuance), the literal syllable
"우" ("preferred" in Korean), an optional trailing "B" (a later-issued
class), and an optional literal "(전환)" (convertible). Examples:
"삼성전자우" (Samsung Electronics, base preferred), "현대차2우B" (Hyundai
Motor, 2nd preferred class B), "CJ4우(전환)" (CJ, 4th convertible
preferred). Stripping this suffix and requiring an EXACT match against an
existing common-share name in the same market is what actually identifies
a real pair -- checked live against the full KOSPI/KOSDAQ universe:

  - 108/110 KOSPI preferred-looking names resolve to a real common-share
    match this way (98%). The 2 that don't ("코리아써우"/"남선알미우") turn
    out to use an ABBREVIATED base name that drops characters from the
    full common name ("코리아써키트"/"남선알미늄") to fit a display-length
    limit -- a real Korean-market naming quirk, not a bug in this script.
    Rather than add fuzzy/prefix matching (which risks wrong pairings
    elsewhere), these 2 are silently dropped, same policy as
    nse_bse_dual_listing_correlation.py drops any pair it can't resolve.

  - KOSDAQ has only 6 names ending in the preferred-suffix pattern, and 3
    of them are FALSE POSITIVES -- genuine company names that happen to
    end in "우" with no preferred-share meaning at all (e.g. "이오플로우"
    / EOFlow, "에코글로우"). These are automatically excluded because their
    stripped "base" ("이오플로", "에코글로") doesn't match any real common
    share name -- the exact-match-against-a-real-name requirement is what
    keeps this robust, not the regex alone. Only the 3 genuine KOSDAQ
    pairs (해성산업1우, 대호특수강우, 소프트센우, all with real common-share
    matches) are kept.

Note this is a genuinely different economic question than NSE/BSE's: a
common/preferred pair are NOT the same security traded on two venues (no
arbitrage forces near-1.0 correlation) -- they're two different securities
of the same company with different dividend/voting rights, so a lower,
more variable correlation than NSE/BSE's ~0.99 is expected and is itself
the finding, not necessarily an error to chase down further. There's no
separate "verify names" pass here (unlike nse_bse_dual_listing_correlation.py)
because the pairing is already name-confirmed at construction time -- a low
correlation here reflects real preferred/common price divergence, not a
ticker-matching mistake.

Usage:
    python3 korea_common_preferred_correlation.py --sample 30
    python3 korea_common_preferred_correlation.py            # full universe (small: ~110 pairs)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

_PREFERRED_SUFFIX = re.compile(r"\d*우[A-Z]?(\(전환\))?$")


def find_preferred_pairs() -> pd.DataFrame:
    """
    Scans KOSPI + KOSDAQ for preferred-share names, strips the suffix, and
    keeps only rows whose stripped base name exactly matches a real
    common-share name in the SAME market. Returns one row per pair:
    common_code, common_name, preferred_code, preferred_name, market.
    """
    import warnings as _w
    _w.filterwarnings("ignore")
    import FinanceDataReader as fdr

    rows = []
    for market, suffix in [("KOSPI", ".KS"), ("KOSDAQ", ".KQ")]:
        df = fdr.StockListing(market)
        df["Name"] = df["Name"].astype(str).str.strip()
        by_name = {name: code for name, code in zip(df["Name"], df["Code"])}
        pref = df[df["Name"].str.contains(_PREFERRED_SUFFIX, regex=True, na=False)]
        for _, r in pref.iterrows():
            pref_name, pref_code = r["Name"], str(r["Code"]).strip()
            base_name = _PREFERRED_SUFFIX.sub("", pref_name).strip()
            if not base_name or base_name == pref_name:
                continue
            common_code = by_name.get(base_name)
            if common_code:
                rows.append({
                    "common_code": str(common_code).strip(), "common_name": base_name,
                    "preferred_code": pref_code, "preferred_name": pref_name,
                    "market": market, "suffix": suffix,
                })
    return pd.DataFrame(rows)


def fetch_pair_prices(pairs: pd.DataFrame, period: str = "1y", batch_size: int = 25) -> dict:
    """
    For each pair, fetches BOTH {common_code}{suffix} and
    {preferred_code}{suffix} in the same yf.download batch call. Returns
    {preferred_code: {"common": Series|None, "preferred": Series|None}}.
    """
    import yfinance as yf

    results: dict = {}
    n_batches = (len(pairs) + batch_size - 1) // batch_size
    for i in range(0, len(pairs), batch_size):
        batch = pairs.iloc[i:i + batch_size]
        yf_tickers = [t for _, r in batch.iterrows()
                      for t in (f"{r['common_code']}{r['suffix']}", f"{r['preferred_code']}{r['suffix']}")]
        batch_num = i // batch_size + 1
        print(f"  [{batch_num}/{n_batches}] fetching {len(batch)} pairs (common+preferred each)...", flush=True)
        try:
            raw = yf.download(yf_tickers, period=period, auto_adjust=True,
                               progress=False, group_by="ticker", threads=True)
        except Exception as exc:
            print(f"    batch failed: {exc}", flush=True)
            continue

        for _, r in batch.iterrows():
            common_sym, pref_sym = f"{r['common_code']}{r['suffix']}", f"{r['preferred_code']}{r['suffix']}"
            try:
                common_close = raw[common_sym]["Close"].dropna()
            except (KeyError, TypeError):
                common_close = None
            try:
                pref_close = raw[pref_sym]["Close"].dropna()
            except (KeyError, TypeError):
                pref_close = None
            results[r["preferred_code"]] = {"common": common_close, "preferred": pref_close}

    return results


def compute_pair_correlations(pairs: pd.DataFrame, prices: dict, min_common_days: int = 60) -> pd.DataFrame:
    """
    For each pair with usable data on both sides, computes the correlation
    of daily returns between the common and preferred quotes, plus the
    latest preferred-to-common price ratio (Korean preferred shares
    typically trade at a discount to common -- this is the expected,
    normal state, not an anomaly by itself).
    """
    rows = []
    for _, r in pairs.iterrows():
        d = prices.get(r["preferred_code"])
        if d is None:
            continue
        common, pref = d.get("common"), d.get("preferred")
        if common is None or pref is None or common.empty or pref.empty:
            continue
        combined = pd.DataFrame({"common": common, "preferred": pref}).dropna()
        if len(combined) < min_common_days:
            continue
        aligned = combined.pct_change().dropna()
        aligned.columns = ["common_ret", "preferred_ret"]
        if len(aligned) < min_common_days:
            continue
        corr = aligned["common_ret"].corr(aligned["preferred_ret"])
        if pd.isna(corr):
            continue
        common_last, pref_last = combined["common"].iloc[-1], combined["preferred"].iloc[-1]
        rows.append({
            "company": r["common_name"],
            "common_code": r["common_code"], "preferred_code": r["preferred_code"],
            "market": r["market"],
            "correlation": round(float(corr), 4),
            "common_days": len(aligned),
            "common_last_close": round(float(common_last), 2),
            "preferred_last_close": round(float(pref_last), 2),
            "preferred_discount_pct": round(100 * (common_last - pref_last) / common_last, 2),
        })

    if not rows:
        return pd.DataFrame(columns=["company", "common_code", "preferred_code", "market",
                                      "correlation", "common_days", "common_last_close",
                                      "preferred_last_close", "preferred_discount_pct"])
    return pd.DataFrame(rows).sort_values("correlation")


def run(
    sample: int = None,
    period: str = "1y",
    anomaly_threshold: float = 0.8,
    output_dir: str = ".",
) -> pd.DataFrame:
    print("Finding Korean common/preferred share pairs (KOSPI + KOSDAQ)...", flush=True)
    pairs = find_preferred_pairs()
    print(f"Found {len(pairs)} pairs with a matching common-share name.", flush=True)
    if sample and sample < len(pairs):
        pairs = pairs.sample(sample, random_state=0).reset_index(drop=True)

    prices = fetch_pair_prices(pairs, period=period)
    result = compute_pair_correlations(pairs, prices)
    n_resolved = len(result)
    print(f"{n_resolved}/{len(pairs)} pairs resolved with usable common history "
          f"on both sides", flush=True)

    out = Path(output_dir)
    result.to_csv(out / "korea_common_preferred_correlations.csv", index=False)

    anomalies = result[result["correlation"] < anomaly_threshold]

    with open(out / "korea_common_preferred_report.txt", "w") as f:
        f.write(f"Korea common/preferred share correlation check -- {n_resolved} pairs "
                f"resolved out of {len(pairs)} found, period={period}\n\n")
        if n_resolved:
            f.write("Correlation distribution (same company, common share vs preferred share):\n")
            f.write(f"  mean:   {result['correlation'].mean():.4f}\n")
            f.write(f"  median: {result['correlation'].median():.4f}\n")
            f.write(f"  min:    {result['correlation'].min():.4f}\n")
            f.write(f"  max:    {result['correlation'].max():.4f}\n")
            f.write(f"  p10:    {result['correlation'].quantile(0.10):.4f}\n\n")
            f.write("Preferred discount to common (typical, not an anomaly by itself):\n")
            f.write(f"  mean:   {result['preferred_discount_pct'].mean():.2f}%\n")
            f.write(f"  median: {result['preferred_discount_pct'].median():.2f}%\n\n")
            f.write(f"Anomalies (correlation < {anomaly_threshold}, {len(anomalies)} found -- "
                    f"real preferred/common price divergence, not a data error, since pairing "
                    f"is name-confirmed at construction time):\n")
            f.write(anomalies.to_string(index=False) if len(anomalies) else "  none\n")
            f.write("\n\nFull results (sorted by correlation, lowest first):\n")
            f.write(result.to_string(index=False))
        else:
            f.write("No pairs resolved with usable history.\n")

    print(f"\nDone. {n_resolved} common/preferred pairs, {len(anomalies)} below the "
          f"{anomaly_threshold} anomaly threshold.", flush=True)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Korea common vs preferred share correlation check")
    ap.add_argument("--sample", type=int, default=None,
                     help="Check a random sample of this many pairs instead of the full set")
    ap.add_argument("--period", default="1y")
    ap.add_argument("--anomaly-threshold", type=float, default=0.8,
                     help="Flag pairs whose correlation is below this as worth investigating")
    ap.add_argument("--output-dir", default=".")
    args = ap.parse_args()

    run(sample=args.sample, period=args.period,
        anomaly_threshold=args.anomaly_threshold, output_dir=args.output_dir)
