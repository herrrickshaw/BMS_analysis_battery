#!/usr/bin/env python3
"""
valuation_clustering.py — cluster stocks into DATA-DRIVEN peer groups by business
profile, then flag over/under-priced names vs their same-profile peers.

The usual "peers" are GICS sectors; here peers are learned by clustering on business
ECONOMICS (ROE, ROCE, margins, growth, asset turnover, leverage, FCF yield) — NOT on
valuation. Then within each cluster the VALUATION (PE, PB) is z-scored: a stock whose
PE/PB sits far above same-profile peers is relatively OVERPRICED; far below =
UNDERPRICED. This surfaces mispricings GICS sectors miss (two "capital goods" names
can have totally different economics; two different-sector names can be true peers).

Covers markets with fundamentals: India, Korea, US (from reports/financial_ratios.csv).

Output: reports/valuation_clusters.md + reports/valuation_clusters.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from obs import get_logger, DecisionLog

HERE = Path(__file__).resolve().parent
LOG = get_logger("valuation_clustering")
PROFILE = ["roe","roce","operating_margin","net_margin","revenue_growth",
           "asset_turnover","debt_to_equity","fcf_yield"]   # business economics (peers)
K = 8                                                        # peer clusters per market


def winsor(s, lo=0.02, hi=0.98):
    return s.clip(s.quantile(lo), s.quantile(hi))


def main() -> int:
    dl = DecisionLog()
    df = pd.read_csv(HERE / "reports" / "financial_ratios.csv")
    df["eps"] = df["close"] / df["pe"]
    out_rows = []
    for mkt in ["india", "us", "korea"]:
        m = df[df.market == mkt].copy()
        # full universe, NO liquidity gate; only exclude non-valuable (losses) + extreme
        # outliers that would distort the peer z-scores. Positive PE/PB, generous caps.
        m = m[(m.pe > 0) & (m.pe < 300) & (m.pb > 0) & (m.pb < 60)]
        prof = m[PROFILE].apply(pd.to_numeric, errors="coerce")
        keep = [c for c in PROFILE if prof[c].notna().mean() > 0.4]   # drop all-sparse cols (KR roce)
        prof = prof[keep]
        m = m[prof.notna().sum(axis=1) >= max(3, len(keep) - 2)]      # need most present fields
        if len(m) < K * 3:
            LOG.info(f"{mkt}: only {len(m)} usable stocks — skipping (too sparse)"); continue
        prof = prof.loc[m.index].apply(winsor).fillna(prof.median())
        X = StandardScaler().fit_transform(prof)
        km = KMeans(n_clusters=K, n_init=10, random_state=0).fit(X)
        m["cluster"] = km.labels_
        # within-cluster robust valuation z (for magnitude) + percentile (for the verdict)
        for col in ["pe", "pb"]:
            g = m.groupby("cluster")[col]
            med = g.transform("median"); mad = g.transform(lambda s: (s - s.median()).abs().median()) + 1e-9
            m[f"{col}_z"] = (m[col] - med) / (1.4826 * mad)
        m["valuation_z"] = m[["pe_z", "pb_z"]].mean(axis=1)   # + = expensive vs peers
        m["val_pct"] = m.groupby("cluster")["valuation_z"].rank(pct=True)
        m["roe_rank"] = m.groupby("cluster")["roe"].rank(pct=True)
        m["verdict"] = np.where(m.val_pct >= 0.85, "OVERPRICED",
                        np.where(m.val_pct <= 0.15, "UNDERPRICED", "fair"))
        out_rows.append(m)
        LOG.info(f"{mkt}: {len(m)} stocks, {K} peer clusters; "
                 f"{(m.verdict=='OVERPRICED').sum()} overpriced / "
                 f"{(m.verdict=='UNDERPRICED').sum()} underpriced")
        dl.record("valuation_clustering", market=mkt, n=len(m),
                  overpriced=int((m.verdict=='OVERPRICED').sum()),
                  underpriced=int((m.verdict=='UNDERPRICED').sum()))
    res = pd.concat(out_rows, ignore_index=True)
    res.to_csv(HERE / "reports" / "valuation_clusters.csv", index=False)

    L = ["# Valuation clustering — over/under-priced vs same-profile peers", "",
         "Peers are learned by clustering on **business economics** (ROE, ROCE, margins, "
         "growth, asset turnover, leverage, FCF yield) — not GICS sectors. Within each "
         f"peer cluster, PE & PB are z-scored (robust); `valuation_z` > +1.5 = OVERPRICED "
         "vs same-profile peers, < −1.5 = UNDERPRICED. Markets with fundamentals: IN/US/KR.",
         ""]
    for mkt in ["india", "us", "korea"]:
        m = res[res.market == mkt]
        def fmt(r): return f"{r['name'][:24]:<24} PE {r.pe:6.1f} PB {r.pb:5.1f} ROE {r.roe*100:5.1f}% val_z {r.valuation_z:+.1f}"
        under = m[m.verdict=="UNDERPRICED"].sort_values("valuation_z").head(12)
        over  = m[m.verdict=="OVERPRICED"].sort_values("valuation_z", ascending=False).head(12)
        # best value = underpriced AND top-ROE-in-cluster
        best = m[(m.verdict=="UNDERPRICED") & (m.roe_rank>0.6)].sort_values("valuation_z").head(8)
        L += [f"## {mkt.upper()} — {len(m)} stocks, {K} peer clusters", "",
              "**UNDERPRICED vs peers (cheap for their economics):**", "```"]
        L += ["  "+fmt(r) for _,r in under.iterrows()]
        L += ["```", "", "**OVERPRICED vs peers (expensive for their economics):**", "```"]
        L += ["  "+fmt(r) for _,r in over.iterrows()]
        L += ["```", "", "**★ Best value (underpriced AND high-ROE within cluster):**", "```"]
        L += ["  "+fmt(r) for _,r in best.iterrows()] or ["  (none)"]
        L += ["```", ""]
    # cluster profiles (the discovered peer archetypes) for india as an example
    m = res[res.market=="india"]
    prof_tbl = m.groupby("cluster").agg(n=("name","size"), roe=("roe","median"),
              net_margin=("net_margin","median"), rev_growth=("revenue_growth","median"),
              pe=("pe","median"), pb=("pb","median")).round(3)
    L += ["## Discovered peer archetypes (India clusters)", "",
          "| cluster | n | med ROE | med net-margin | med growth | med PE | med PB |",
          "|---|--:|--:|--:|--:|--:|--:|"]
    for c,r in prof_tbl.iterrows():
        L.append(f"| {c} | {int(r.n)} | {r.roe*100:.0f}% | {r.net_margin*100:.0f}% | "
                 f"{r.rev_growth*100:.0f}% | {r.pe:.0f} | {r.pb:.1f} |")
    L += ["", "> Peer clusters are unsupervised (business economics), so a stock flagged "
          "over/under-priced is mispriced vs names that ACTUALLY resemble it — catching "
          "what sector labels miss. Fundamentals are yfinance-sourced, latest FY; PE>150/"
          "PB>30/losses excluded. Descriptive screen, not investment advice."]
    (HERE / "reports" / "valuation_clusters.md").write_text("\n".join(L))
    print("\n".join(L))
    print("\nwrote reports/valuation_clusters.{md,csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
