#!/usr/bin/env python3
"""
nse_bse_dual_listing_correlation.py
=====================================
Do NSE and BSE quotes of the SAME stock move together?

For companies genuinely dual-listed on both NSE and BSE, the same alpha
ticker symbol (e.g. RELIANCE) resolves to real, distinct yfinance quotes
under both suffixes -- RELIANCE.NS (NSE) and RELIANCE.BO (BSE). Since these
represent literally the same underlying equity traded on two venues within
the same country, same-day correlation between the two quotes should be
extremely high (near 1.0) -- any material divergence would either be an
arbitrage opportunity, a data/ticker-matching artifact, or a genuine
liquidity/microstructure quirk worth flagging.

Unlike market_correlation_scan.py's --market BSE (which scans BSE-ONLY
listings, explicitly excluding anything also on NSE -- see
symbol_master.py's _bse_names()), this script targets exactly the
opposite: pairs where the SAME company trades on BOTH exchanges. It
doesn't rely on _bse_names() at all -- dual-listed large/mid-caps
reliably resolve on yfinance under the SAME alpha ticker with a .BO
suffix, so this just tries both suffixes per NSE symbol and keeps
whichever ones resolve on both.

IMPORTANT, discovered while validating this against real data: "resolves
on both exchanges" is NOT the same as "actively trades on both exchanges."
RELIANCE.BO and INFY.BO technically exist but had only 2 trading days of
data over a full year (vs. 249 on NSE) -- essentially all real trading
volume for those mega-caps has migrated to NSE, leaving the BSE listing
dormant. TCS.BO, by contrast, had 247 common days and a genuine 0.997
NSE/BSE correlation. min_common_days (default 60) exists specifically to
filter out these sparse-data pairs rather than report a spurious
near-perfect correlation computed from a handful of stale data points --
don't lower it casually, that's the mechanism that keeps the reported
correlations meaningful.

Usage:
    python3 nse_bse_dual_listing_correlation.py --sample 300
    python3 nse_bse_dual_listing_correlation.py            # full NSE universe (slow: 2 fetches/symbol)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))


def fetch_dual_listing_prices(symbols: list, period: str = "1y", batch_size: int = 25) -> dict:
    """
    For each symbol, fetches BOTH {symbol}.NS and {symbol}.BO in the same
    yf.download batch call. Returns {symbol: {"nse": Series|None, "bse": Series|None}}.
    batch_size counts SYMBOLS, not tickers -- each symbol requests 2 tickers,
    so the actual yf.download batch is 2x this size.
    """
    import yfinance as yf

    results: dict = {}
    n_batches = (len(symbols) + batch_size - 1) // batch_size
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        yf_tickers = [t for s in batch for t in (f"{s}.NS", f"{s}.BO")]
        batch_num = i // batch_size + 1
        print(f"  [{batch_num}/{n_batches}] fetching {len(batch)} symbols (NSE+BSE each)...", flush=True)
        try:
            raw = yf.download(yf_tickers, period=period, auto_adjust=True,
                               progress=False, group_by="ticker", threads=True)
        except Exception as exc:
            print(f"    batch failed: {exc}", flush=True)
            continue

        for s in batch:
            ns_sym, bo_sym = f"{s}.NS", f"{s}.BO"
            try:
                ns_close = raw[ns_sym]["Close"].dropna()
            except (KeyError, TypeError):
                ns_close = None
            try:
                bo_close = raw[bo_sym]["Close"].dropna()
            except (KeyError, TypeError):
                bo_close = None
            results[s] = {"nse": ns_close, "bse": bo_close}

    return results


def compute_dual_listing_correlations(dual_prices: dict, min_common_days: int = 60) -> pd.DataFrame:
    """
    For each symbol with usable data on BOTH exchanges, computes the
    correlation of daily returns between its NSE and BSE quotes (same
    underlying company, two venues). Also reports the latest same-day
    price gap between the two quotes as a sanity check -- a genuinely
    dual-listed stock's NSE/BSE prices should track closely, with any
    persistent gap bounded by arbitrage costs.
    """
    rows = []
    for symbol, d in dual_prices.items():
        ns, bo = d.get("nse"), d.get("bse")
        if ns is None or bo is None or ns.empty or bo.empty:
            continue
        combined = pd.DataFrame({"nse": ns, "bse": bo}).dropna()
        if len(combined) < min_common_days:
            continue
        aligned = combined.pct_change().dropna()
        aligned.columns = ["nse_ret", "bse_ret"]
        if len(aligned) < min_common_days:
            continue
        corr = aligned["nse_ret"].corr(aligned["bse_ret"])
        if pd.isna(corr):
            continue
        nse_last, bse_last = combined["nse"].iloc[-1], combined["bse"].iloc[-1]
        rows.append({
            "symbol": symbol,
            "correlation": round(float(corr), 4),
            "common_days": len(aligned),
            "nse_last_close": round(float(nse_last), 2),
            "bse_last_close": round(float(bse_last), 2),
            "price_gap_pct": round(100 * (nse_last - bse_last) / bse_last, 3),
        })

    if not rows:
        return pd.DataFrame(columns=["symbol", "correlation", "common_days",
                                      "nse_last_close", "bse_last_close", "price_gap_pct"])
    return pd.DataFrame(rows).sort_values("correlation")


# Legal-form/filler tokens stripped before comparing two company names --
# mirrors symbol_master.clean_name's approach, plus fund-specific filler
# (ETF/MF/S&P) since a meaningful fraction of "dual-listed" false alarms
# turned out to be the same mutual-fund ETF product named slightly
# differently across exchanges (e.g. "LIC MF BSE Sensex ETF" vs
# "LIC MF ETF Sensex" -- same fund, word order differs).
_NAME_FILLER_TOKENS = {
    "LIMITED", "LTD", "PVT", "PRIVATE", "CORP", "CORPORATION", "CO", "INC",
    "PLC", "THE", "OF", "AND", "&", "MF", "ETF", "S&P", "INDIA",
}


def _name_tokens(name) -> set:
    if not isinstance(name, str):
        return set()
    up = re.sub(r"[^A-Za-z0-9 ]", " ", name.upper())
    return {t for t in up.split() if t and t not in _NAME_FILLER_TOKENS and len(t) >= 2}


def verify_dual_listing_names(anomalies: pd.DataFrame, sleep_between: float = 0.0) -> pd.DataFrame:
    """
    For each row in *anomalies* (typically the low-correlation subset from
    compute_dual_listing_correlations), fetches both exchanges' company
    names via yfinance and checks whether they plausibly refer to the same
    company -- a token-set overlap check (after stripping legal-form/fund
    filler words), NOT naive substring matching, which produced false
    positives on real data during development ("3P Land Holdings Ltd" vs
    "...Limited", and multiple ETF products with reordered name tokens,
    both looked like "different companies" under plain substring
    containment despite being the identical entity).

    Adds two columns: nse_name, bse_name, same_company (True/False/None --
    None means at least one side's name couldn't be fetched, not verified
    either way). A low correlation with same_company=False is the genuine
    signal worth investigating (a real ticker collision between two
    unrelated companies, not a data/liquidity artifact); same_company=True
    means the low correlation is coming from somewhere else (illiquidity,
    stale quotes on one side, a corporate action reflected asynchronously).
    """
    import time
    import yfinance as yf

    rows = []
    for symbol in anomalies["symbol"]:
        try:
            ns_name = yf.Ticker(f"{symbol}.NS").info.get("longName", "")
        except Exception:
            ns_name = ""
        try:
            bo_name = yf.Ticker(f"{symbol}.BO").info.get("longName", "")
        except Exception:
            bo_name = ""
        rows.append({"symbol": symbol, "nse_name": ns_name, "bse_name": bo_name})
        if sleep_between:
            time.sleep(sleep_between)

    names_df = pd.DataFrame(rows)
    merged = anomalies.merge(names_df, on="symbol", how="left")

    def _same(row):
        ta, tb = _name_tokens(row["nse_name"]), _name_tokens(row["bse_name"])
        if not ta or not tb:
            return None
        return (len(ta & tb) / min(len(ta), len(tb))) >= 0.6

    merged["same_company"] = merged.apply(_same, axis=1)
    return merged


def run(
    symbols: list = None,
    sample: int = None,
    period: str = "1y",
    anomaly_threshold: float = 0.8,
    output_dir: str = ".",
) -> pd.DataFrame:
    if symbols is None:
        from symbol_master import load_master
        df = load_master(auto_refresh=False)
        symbols = df[df["exchange"] == "NSE"]["symbol"].tolist()
    if sample:
        import random
        random.seed(0)
        symbols = random.sample(symbols, min(sample, len(symbols)))

    print(f"Checking {len(symbols)} NSE symbols for a resolvable BSE dual listing...", flush=True)
    dual_prices = fetch_dual_listing_prices(symbols, period=period)
    result = compute_dual_listing_correlations(dual_prices)
    n_dual_listed = len(result)
    print(f"{n_dual_listed}/{len(symbols)} symbols are genuinely dual-listed "
          f"(both NSE and BSE quotes resolved with usable history)", flush=True)

    out = Path(output_dir)
    result.to_csv(out / "nse_bse_dual_listing_correlations.csv", index=False)

    anomalies = result[result["correlation"] < anomaly_threshold]
    verified = pd.DataFrame()
    n_collisions = 0
    if len(anomalies):
        print(f"Verifying company names for {len(anomalies)} low-correlation pairs "
              f"(distinguishing real ticker collisions from illiquidity noise)...", flush=True)
        verified = verify_dual_listing_names(anomalies)
        verified.to_csv(out / "nse_bse_dual_listing_anomalies_verified.csv", index=False)
        n_collisions = int((verified["same_company"] == False).sum())  # noqa: E712

    with open(out / "nse_bse_dual_listing_report.txt", "w") as f:
        f.write(f"NSE/BSE dual-listing correlation check -- {n_dual_listed} dual-listed "
                f"symbols found out of {len(symbols)} checked, period={period}\n\n")
        if n_dual_listed:
            f.write("Correlation distribution (same company, NSE quote vs BSE quote):\n")
            f.write(f"  mean:   {result['correlation'].mean():.4f}\n")
            f.write(f"  median: {result['correlation'].median():.4f}\n")
            f.write(f"  min:    {result['correlation'].min():.4f}\n")
            f.write(f"  max:    {result['correlation'].max():.4f}\n")
            f.write(f"  p10:    {result['correlation'].quantile(0.10):.4f}\n\n")
            f.write(f"Anomalies (correlation < {anomaly_threshold}, {len(anomalies)} found):\n")
            f.write(anomalies.to_string(index=False) if len(anomalies) else "  none\n")
            if len(verified):
                f.write(f"\n\nName verification of anomalies -- {n_collisions} CONFIRMED as genuine "
                        f"ticker collisions (different companies sharing a symbol string across "
                        f"exchanges), {int((verified['same_company'] == True).sum())} confirmed same "  # noqa: E712
                        f"company (low correlation is illiquidity/stale-quote noise, not a data "
                        f"error), {int(verified['same_company'].isna().sum())} unverifiable "
                        f"(name lookup failed on at least one side):\n")
                collisions = verified[verified["same_company"] == False]  # noqa: E712
                if len(collisions):
                    f.write("\nCONFIRMED COLLISIONS (different companies -- not a real dual listing):\n")
                    f.write(collisions[["symbol", "nse_name", "bse_name", "correlation", "price_gap_pct"]]
                            .to_string(index=False))
                    f.write("\n")
            f.write("\n\nFull results (sorted by correlation, lowest first):\n")
            f.write(result.to_string(index=False))
        else:
            f.write("No dual-listed symbols found in this sample.\n")

    print(f"\nDone. {n_dual_listed} dual-listed symbols, {len(anomalies)} below the "
          f"{anomaly_threshold} anomaly threshold, {n_collisions} confirmed genuine ticker "
          f"collisions (not real dual listings).", flush=True)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NSE vs BSE dual-listing correlation check")
    ap.add_argument("--sample", type=int, default=None,
                     help="Check a random sample of this many NSE symbols instead of the full universe")
    ap.add_argument("--period", default="1y")
    ap.add_argument("--anomaly-threshold", type=float, default=0.8,
                     help="Flag dual-listed pairs whose correlation is below this as worth investigating")
    ap.add_argument("--output-dir", default=".")
    args = ap.parse_args()

    run(sample=args.sample, period=args.period,
        anomaly_threshold=args.anomaly_threshold, output_dir=args.output_dir)
