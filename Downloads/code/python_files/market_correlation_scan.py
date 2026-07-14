#!/usr/bin/env python3
"""
market_correlation_scan.py
============================
Full-universe correlation scan: which stocks in a given market move
together? (Originally nse_correlation_scan.py -- generalized to cover any
market in symbol_master, e.g. NSE or US/NASDAQ+NYSE.)

Builds a correlation matrix across a whole market's symbol_master universe
(or any provided symbol list), then reports which stocks cluster together
(connected components at a given correlation threshold) -- the same
correlation-network technique in portfolio_analysis.plot_correlation_network,
extended to run over an entire market instead of a hand-picked basket.

At full-universe scale (thousands of stocks) a node-and-edge chart of
everything isn't legible, so this reports the real numbers as data (full
correlation matrix CSV + a text cluster report) and only charts the
top-N largest clusters, reusing plot_correlation_network's existing
rendering for each one.

Usage:
    python3 market_correlation_scan.py --market NSE              # full NSE universe
    python3 market_correlation_scan.py --market US                # full US (NASDAQ+NYSE) universe
    python3 market_correlation_scan.py --market BSE               # full BSE-only universe
    python3 market_correlation_scan.py --market JAPAN             # full TSE universe
    python3 market_correlation_scan.py --market KOREA             # full KOSPI+KOSDAQ universe
    python3 market_correlation_scan.py --market CHINA             # full SSE+SZSE A-share universe
    python3 market_correlation_scan.py --market HK                # full HKEX universe
    python3 market_correlation_scan.py --market EUROPE            # full 17-exchange European universe
    python3 market_correlation_scan.py --market US --sample 300   # a 300-stock US sample
    python3 market_correlation_scan.py --market NSE --threshold 0.6 --top-clusters 5

Note on --market BSE: symbol_master's BSE rows are BSE-ONLY listings --
_bse_names() deliberately excludes any symbol also listed on NSE (dual
listings are represented once, under their NSE row). So --market BSE scans
distinct, single-exchange BSE companies, NOT the dual-listed ones. For
whether NSE/BSE dual-listed stocks move together, see
nse_bse_dual_listing_correlation.py instead -- a different question this
module's per-market scan can't answer, since a dual-listed stock's BSE
quote never appears here as a separate row to correlate against its NSE one.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import networkx as nx
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for portfolio_analysis

# Per CLAUDE.md's ticker-format table: India stores bare NSE symbols (needs
# .NS appended for yfinance); US/Japan/Korea store symbols already
# pre-suffixed/usable as-is (yf_suffix="" for all three -- Japan and Korea's
# symbol_master rows already embed .T/.KS/.KQ, same reasoning as US's bare
# tickers needing nothing appended).
MARKET_EXCHANGES = {
    "NSE": ["NSE"],
    "US": ["NASDAQ", "NYSE"],
    "BSE": ["BSE"],
    "JAPAN": ["JAPAN"],
    "KOREA": ["KOSPI", "KOSDAQ"],
    "CHINA": ["SSE", "SZSE"],
    "HK": ["HKEX"],
    "EUROPE": [
        "London Stock Exchange", "Deutsche Boerse Frankfurt", "Borsa Italiana",
        "Euronext Paris", "Euronext Amsterdam", "Euronext Brussels",
        "Euronext Dublin", "Euronext Lisbon", "BME Madrid",
        "Nasdaq Stockholm", "Nasdaq Copenhagen", "Nasdaq Helsinki",
        "Athens Stock Exchange", "Oslo Bors", "SIX Swiss", "Vienna", "Warsaw GPW",
    ],
}
MARKET_YF_SUFFIX = {
    "NSE": ".NS",
    "US": "",
    "JAPAN": "",
    "KOREA": "",
    "HK": "",
    "BSE": ".BO",
    "CHINA": "",
    "EUROPE": "",
}


def load_universe(market: str) -> list:
    """Full symbol list for *market* from the symbol_master cache (see symbol_master.py)."""
    from symbol_master import load_master
    df = load_master(auto_refresh=False)
    exchanges = MARKET_EXCHANGES[market]
    return df[df["exchange"].isin(exchanges)]["symbol"].tolist()


def fetch_universe_prices(
    symbols: list,
    period: str = "1y",
    batch_size: int = 50,
    min_history: int = 100,
    yf_suffix: str = ".NS",
    sleep_between: float = 0.0,
) -> pd.DataFrame:
    """
    Batched yf.download across the whole *symbols* list (same "batches of 50"
    strategy db/bulk_fetcher.py uses for the platform's full-universe OHLCV
    prefetch), returning one aligned close-price DataFrame. Symbols that fail
    to fetch or don't have at least *min_history* daily observations are
    silently dropped -- expected at this scale (delistings, illiquid/renamed
    tickers), not a bug.

    *sleep_between* (seconds, default 0 = no change to prior behavior): pause
    after every batch. yfinance's bulk downloader swallows per-ticker
    rate-limit errors internally (YFRateLimitError) rather than raising at
    the top level, so a burst of ~1,100+ requests can silently degrade an
    entire scan to 0 resolved symbols with no exception to catch -- seen
    live on the HK scan (5,203-symbol China scan run immediately before it
    exhausted the window; a same-day retry still failed after ~23 clean
    batches). A fixed inter-batch delay is the simple fix; a fancier
    detect-and-backoff-on-empty-batch scheme isn't needed for a scan that
    is already run interactively/in the background, not on a deadline.
    """
    frames = []
    n_batches = (len(symbols) + batch_size - 1) // batch_size
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        yf_symbols = [f"{s}{yf_suffix}" if yf_suffix and "." not in s else s for s in batch]
        batch_num = i // batch_size + 1
        print(f"  [{batch_num}/{n_batches}] fetching {len(batch)} symbols...", flush=True)
        try:
            raw = yf.download(yf_symbols, period=period, auto_adjust=True,
                               progress=False, group_by="ticker", threads=True)
        except Exception as exc:
            print(f"    batch failed: {exc}", flush=True)
            if sleep_between:
                time.sleep(sleep_between)
            continue
        for sym, yf_sym in zip(batch, yf_symbols):
            try:
                close = (raw[yf_sym]["Close"] if len(yf_symbols) > 1 else raw["Close"])
            except (KeyError, TypeError):
                continue
            close = close.dropna()
            if len(close) >= min_history:
                frames.append(close.rename(sym))

        if sleep_between and batch_num < n_batches:
            time.sleep(sleep_between)

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


def build_mst(corr: pd.DataFrame) -> nx.Graph:
    """
    Mantegna's (1999) minimum spanning tree construction: converts each
    pairwise correlation to a metric distance d_ij = sqrt(2*(1-rho_ij)) (0
    for rho=1, 2 for rho=-1, satisfies the triangle inequality) and builds
    the MST via Kruskal's algorithm. Always exactly N-1 edges, no cycles --
    structurally cannot produce the "everything transitively chains
    together via broad market beta" giant blob that naive threshold +
    connected-components suffers from at full-universe scale (see this
    module's earlier NSE/US scan results: 57%/37% of the resolved universe
    swept into one component at threshold=0.55). MST only ever picks the
    single lowest-distance edge to connect each new node, so a spurious
    high-correlation shortcut between two otherwise-unrelated sectors can't
    inflate the "cluster" the way it can under naive thresholding.
    """
    symbols = list(corr.index)
    G = nx.Graph()
    G.add_nodes_from(symbols)
    for i, a in enumerate(symbols):
        for b in symbols[i + 1:]:
            c = corr.loc[a, b]
            if pd.notna(c):
                dist = (2 * (1 - c)) ** 0.5
                G.add_edge(a, b, weight=dist, corr=float(c))
    return nx.minimum_spanning_tree(G, weight="weight")


def mst_clusters(mst: nx.Graph, min_corr_to_keep_edge: float = 0.7) -> list:
    """
    Cuts the MST into sub-trees ("clusters") by dropping edges whose
    original correlation is below min_corr_to_keep_edge -- equivalent to
    single-linkage hierarchical clustering cut at that correlation level.

    IMPORTANT, empirically-discovered caveat: this needs a HIGHER cutoff
    than compute_correlation_clusters' naive threshold to show comparable
    granularity, not the same value. Verified against the real full NSE
    universe correlation matrix (2,225 symbols): min_corr_to_keep_edge=0.55
    (matching the naive threshold default) reproduced essentially the same
    ~57%-of-universe giant component as naive thresholding -- MST alone
    does NOT fix the giant-component problem at that cutoff. The reason:
    MST edges are already pre-filtered to the single strongest connection
    needed per node, so a nominal correlation cutoff prunes far fewer of
    them than it would prune from the full all-pairs graph. On that same
    NSE matrix, 0.7 broke the giant component down to ~23% of the universe
    and 0.8 to ~11%, revealing clean real sector groups (fertilizer
    producers, cable TV operators, QSR franchise operators, pharma pairs)
    -- so 0.7 is used as this function's default, not 0.55. Tune per
    dataset; there's no universal "right" cutoff -- inspect a few
    thresholds the way this was validated, don't assume one number
    transfers across markets/periods.
    """
    pruned = nx.Graph()
    pruned.add_nodes_from(mst.nodes())
    for a, b, data in mst.edges(data=True):
        if data.get("corr", -1.0) >= min_corr_to_keep_edge:
            pruned.add_edge(a, b)
    clusters = [c for c in nx.connected_components(pruned) if len(c) > 1]
    clusters.sort(key=len, reverse=True)
    return clusters


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
    market: str = "NSE",
    symbols: list = None,
    sample: int = None,
    period: str = "1y",
    threshold: float = None,
    clustering: str = "threshold",
    top_clusters_to_chart: int = 4,
    output_dir: str = ".",
    sleep_between: float = 0.0,
) -> dict:
    market = market.upper()
    if symbols is None:
        symbols = load_universe(market)
    if sample:
        import random
        random.seed(0)
        symbols = random.sample(symbols, min(sample, len(symbols)))

    # MST needs a substantially higher cutoff than naive thresholding to show
    # comparable granularity -- see mst_clusters' docstring for the empirical
    # NSE finding. Don't silently reuse the naive default across both modes.
    if threshold is None:
        threshold = 0.7 if clustering == "mst" else 0.55

    yf_suffix = MARKET_YF_SUFFIX[market]
    print(f"Scanning {len(symbols)} {market} symbols (period={period})...", flush=True)
    prices = fetch_universe_prices(symbols, period=period, yf_suffix=yf_suffix,
                                    sleep_between=sleep_between)
    print(f"{prices.shape[1]}/{len(symbols)} symbols resolved with usable history", flush=True)

    if clustering == "mst":
        # Mantegna MST: structurally limited to N-1 edges, so a dominant
        # market-mode eigenvalue can't inflate arbitrarily many pairwise
        # correlations the way it can under naive thresholding -- but it
        # still needs its own (higher) cutoff tuned for the dataset, it
        # isn't a parameter-free fix. See mst_clusters' docstring.
        returns = prices.pct_change().dropna(how="all")
        corr = returns.corr(min_periods=60)
        mst = build_mst(corr)
        clusters = mst_clusters(mst, min_corr_to_keep_edge=threshold)
    else:
        corr, clusters = compute_correlation_clusters(prices, threshold=threshold)

    out = Path(output_dir)
    prefix = market.lower()
    corr.to_csv(out / f"{prefix}_correlation_matrix.csv")
    pairs_df = top_pairs(corr, n=30)
    pairs_df.to_csv(out / f"{prefix}_top_correlated_pairs.csv", index=False)

    with open(out / f"{prefix}_correlation_clusters.txt", "w") as f:
        f.write(f"{market} correlation scan -- {prices.shape[1]} symbols, period={period}, "
                f"threshold={threshold}, clustering={clustering}\n\n")
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
                save_path=str(out / f"{prefix}_cluster_{idx + 1}.png"),
            )

    print(f"\nDone. {len(clusters)} clusters, {prices.shape[1]} symbols with data.", flush=True)
    return {"correlation": corr, "clusters": clusters, "prices": prices}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Full-universe market correlation scan")
    ap.add_argument("--market", choices=["NSE", "US", "BSE", "JAPAN", "KOREA", "CHINA", "HK", "EUROPE"], default="NSE")
    ap.add_argument("--sample", type=int, default=None,
                     help="Scan a random sample of this many symbols instead of the full universe")
    ap.add_argument("--period", default="1y")
    ap.add_argument("--threshold", type=float, default=None,
                     help="Correlation cutoff. Defaults to 0.55 for --clustering threshold, "
                          "0.7 for --clustering mst (MST needs a higher cutoff for comparable "
                          "granularity -- see mst_clusters' docstring)")
    ap.add_argument("--clustering", choices=["threshold", "mst"], default="threshold",
                     help="'threshold' = naive threshold + connected-components (can produce a giant "
                          "market-beta blob at full-universe scale); 'mst' = Mantegna minimum spanning "
                          "tree, structurally avoids that failure mode (see build_mst's docstring)")
    ap.add_argument("--top-clusters", type=int, default=4,
                     help="Chart only this many of the largest clusters (full-universe graphs aren't legible)")
    ap.add_argument("--output-dir", default=".")
    ap.add_argument("--sleep-between", type=float, default=0.0,
                     help="Seconds to pause after every batch (default 0 = no pause). Use when "
                          "yfinance's rate limiter silently degrades a scan to 0 resolved symbols "
                          "-- see fetch_universe_prices' docstring")
    args = ap.parse_args()

    run(market=args.market, sample=args.sample, period=args.period, threshold=args.threshold,
        clustering=args.clustering, top_clusters_to_chart=args.top_clusters, output_dir=args.output_dir,
        sleep_between=args.sleep_between)
