#!/usr/bin/env python3
"""
nse_correlation_scan.py
========================
Full-universe correlation scan: which NSE stocks move together?

Builds a correlation matrix across the whole NSE symbol_master universe
(or any provided symbol list), then reports which stocks cluster together
(connected components at a given correlation threshold) -- the same
correlation-network technique in portfolio_analysis.plot_correlation_network,
extended to run over an entire market instead of a hand-picked basket.

At full-universe scale (~2,370 NSE stocks) a node-and-edge chart of
everything isn't legible, so this reports the real numbers as data (full
correlation matrix CSV + a text cluster report) and only charts the
top-N largest clusters, reusing plot_correlation_network's existing
rendering for each one.

Usage:
    python3 nse_correlation_scan.py                       # full NSE universe
    python3 nse_correlation_scan.py --sample 300           # a 300-stock sample
    python3 nse_correlation_scan.py --threshold 0.6 --top-clusters 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for portfolio_analysis


def load_nse_universe() -> list:
    """Full NSE symbol list from the symbol_master cache (see symbol_master.py)."""
    from symbol_master import load_master
    df = load_master(auto_refresh=False)
    return df[df["exchange"] == "NSE"]["symbol"].tolist()


def fetch_universe_prices(
    symbols: list,
    period: str = "1y",
    batch_size: int = 50,
    min_history: int = 100,
) -> pd.DataFrame:
    """
    Batched yf.download across the whole *symbols* list (same "batches of 50"
    strategy db/bulk_fetcher.py uses for the platform's full-universe OHLCV
    prefetch), returning one aligned close-price DataFrame. Symbols that fail
    to fetch or don't have at least *min_history* daily observations are
    silently dropped -- expected at this scale (delistings, illiquid/renamed
    tickers), not a bug.
    """
    frames = []
    n_batches = (len(symbols) + batch_size - 1) // batch_size
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        yf_symbols = [f"{s}.NS" if "." not in s else s for s in batch]
        batch_num = i // batch_size + 1
        print(f"  [{batch_num}/{n_batches}] fetching {len(batch)} symbols...", flush=True)
        try:
            raw = yf.download(yf_symbols, period=period, auto_adjust=True,
                               progress=False, group_by="ticker", threads=True)
        except Exception as exc:
            print(f"    batch failed: {exc}", flush=True)
            continue
        for sym, yf_sym in zip(batch, yf_symbols):
            try:
                close = (raw[yf_sym]["Close"] if len(yf_symbols) > 1 else raw["Close"])
            except (KeyError, TypeError):
                continue
            close = close.dropna()
            if len(close) >= min_history:
                frames.append(close.rename(sym))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def compute_correlation_clusters(
    prices: pd.DataFrame,
    threshold: float = 0.55,
    min_common_days: int = 60,
) -> tuple:
    """
    Returns (correlation_matrix, clusters) where clusters is a list of sets
    of symbols, each mutually connected at |corr| >= threshold via at least
    one edge (connected components, not full pairwise agreement -- same
    semantics as plot_correlation_network's graph).
    """
    returns = prices.pct_change().dropna(how="all")
    corr = returns.corr(min_periods=min_common_days)

    G = nx.Graph()
    G.add_nodes_from(corr.index)
    symbols = list(corr.index)
    for i, a in enumerate(symbols):
        for b in symbols[i + 1:]:
            c = corr.loc[a, b]
            if pd.notna(c) and abs(c) >= threshold:
                G.add_edge(a, b, weight=float(c))

    clusters = [c for c in nx.connected_components(G) if len(c) > 1]
    clusters.sort(key=len, reverse=True)
    return corr, clusters


def top_pairs(corr: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    pairs = []
    symbols = list(corr.index)
    for i, a in enumerate(symbols):
        for b in symbols[i + 1:]:
            c = corr.loc[a, b]
            if pd.notna(c):
                pairs.append((a, b, c))
    return (pd.DataFrame(pairs, columns=["stock_a", "stock_b", "corr"])
            .sort_values("corr", ascending=False).head(n))


def run(
    symbols: list = None,
    sample: int = None,
    period: str = "1y",
    threshold: float = 0.55,
    top_clusters_to_chart: int = 4,
    output_dir: str = ".",
) -> dict:
    if symbols is None:
        symbols = load_nse_universe()
    if sample:
        import random
        random.seed(0)
        symbols = random.sample(symbols, min(sample, len(symbols)))

    print(f"Scanning {len(symbols)} NSE symbols (period={period})...", flush=True)
    prices = fetch_universe_prices(symbols, period=period)
    print(f"{prices.shape[1]}/{len(symbols)} symbols resolved with usable history", flush=True)

    corr, clusters = compute_correlation_clusters(prices, threshold=threshold)

    out = Path(output_dir)
    corr.to_csv(out / "nse_correlation_matrix.csv")
    pairs_df = top_pairs(corr, n=30)
    pairs_df.to_csv(out / "nse_top_correlated_pairs.csv", index=False)

    with open(out / "nse_correlation_clusters.txt", "w") as f:
        f.write(f"NSE correlation scan -- {prices.shape[1]} symbols, period={period}, "
                f"threshold={threshold}\n\n")
        f.write(f"{len(clusters)} clusters found (size > 1):\n\n")
        for c in clusters:
            f.write(f"  ({len(c)}) {sorted(c)}\n")
        f.write("\nTop 30 correlated pairs:\n")
        f.write(pairs_df.to_string(index=False))

    # Chart only the largest clusters -- a full-universe graph isn't legible.
    if top_clusters_to_chart and clusters:
        import matplotlib
        matplotlib.use("Agg")
        import portfolio_analysis as pa
        for idx, cluster in enumerate(clusters[:top_clusters_to_chart]):
            cluster_symbols = sorted(cluster)
            pa.plot_correlation_network(
                cluster_symbols, prices[cluster_symbols], edge_threshold=threshold,
                save_path=str(out / f"nse_cluster_{idx + 1}.png"),
            )

    print(f"\nDone. {len(clusters)} clusters, {prices.shape[1]} symbols with data.", flush=True)
    return {"correlation": corr, "clusters": clusters, "prices": prices}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Full-universe NSE correlation scan")
    ap.add_argument("--sample", type=int, default=None,
                     help="Scan a random sample of this many NSE symbols instead of the full universe")
    ap.add_argument("--period", default="1y")
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--top-clusters", type=int, default=4,
                     help="Chart only this many of the largest clusters (full-universe graphs aren't legible)")
    ap.add_argument("--output-dir", default=".")
    args = ap.parse_args()

    run(sample=args.sample, period=args.period, threshold=args.threshold,
        top_clusters_to_chart=args.top_clusters, output_dir=args.output_dir)
