#!/usr/bin/env python3
# build_europe_broad_list.py
# ==========================
# Regenerate data/europe_broad_list.csv — the broad European scan universe.
#
# WHY THIS EXISTS
# ---------------
# The broad list was previously an untracked CSV that the ~/Downloads wipe destroyed.
# This builder makes it *regenerable from a git-tracked seed* so it can never be
# permanently lost again:
#
#   seed  =  ~/data/europe_all_list.csv          (966 stocks, 17 exchanges — the
#            herrrickshaw app list, committed to git and therefore wipe-proof)
#   plus  =  a curated EMERGING-EUROPE block      (Istanbul .IS, Prague .PR,
#            Budapest .BD, Baltics .TL/.RG/.VS, Iceland .IC)
#   ->       data/europe_broad_list.csv           (~1,000+ tickers, 22 exchanges)
#
# Columns match the seed: yf_ticker,name,index,exchange
#
# The emerging block below is a high-confidence subset of liquid constituents.
# Run with --validate to yfinance-check every ticker (5-day download) and drop
# any that return no data — the same pruning used when the list was first built
# (KOZAL.IS, CETV.PR, MAREL.IC etc. were dropped this way).
#
# Usage:
#   python build_europe_broad_list.py                 # rebuild from tracked seed
#   python build_europe_broad_list.py --validate      # + drop no-data tickers
#   python build_europe_broad_list.py --seed PATH     # override seed location

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
HOME = Path(os.path.expanduser("~"))
OUT = HERE / "data" / "europe_broad_list.csv"

# Seed candidates, most-preferred first (all git-tracked → wipe-proof).
SEED_CANDIDATES = [
    HOME / "data" / "europe_all_list.csv",
    HERE / "data" / "europe_all_list.csv",
]

# ── Emerging-Europe constituents (curated, high-confidence Yahoo tickers) ─────
# These markets are momentum-only under yfinance (no financial statements), so
# they only ever produce Darvas signals — never Piotroski/Coffee-Can picks.
# (name, yf_ticker, index, exchange)
EMERGING = [
    # ── Istanbul BIST (.IS) ──
    ("Turkish Airlines", "THYAO.IS", "BIST100", "Istanbul"),
    ("Garanti BBVA", "GARAN.IS", "BIST100", "Istanbul"),
    ("Akbank", "AKBNK.IS", "BIST100", "Istanbul"),
    ("Isbank C", "ISCTR.IS", "BIST100", "Istanbul"),
    ("Yapi Kredi", "YKBNK.IS", "BIST100", "Istanbul"),
    ("Koc Holding", "KCHOL.IS", "BIST100", "Istanbul"),
    ("Sabanci Holding", "SAHOL.IS", "BIST100", "Istanbul"),
    ("BIM", "BIMAS.IS", "BIST100", "Istanbul"),
    ("Eregli Demir Celik", "EREGL.IS", "BIST100", "Istanbul"),
    ("Tupras", "TUPRS.IS", "BIST100", "Istanbul"),
    ("Aselsan", "ASELS.IS", "BIST100", "Istanbul"),
    ("Sisecam", "SISE.IS", "BIST100", "Istanbul"),
    ("Ford Otosan", "FROTO.IS", "BIST100", "Istanbul"),
    ("Tofas", "TOASO.IS", "BIST100", "Istanbul"),
    ("Turkcell", "TCELL.IS", "BIST100", "Istanbul"),
    ("Pegasus", "PGSUS.IS", "BIST100", "Istanbul"),
    ("Sasa Polyester", "SASA.IS", "BIST100", "Istanbul"),
    ("Kardemir D", "KRDMD.IS", "BIST100", "Istanbul"),
    ("Petkim", "PETKM.IS", "BIST100", "Istanbul"),
    ("Arcelik", "ARCLK.IS", "BIST100", "Istanbul"),
    ("TAV Havalimanlari", "TAVHL.IS", "BIST100", "Istanbul"),
    ("Enka Insaat", "ENKAI.IS", "BIST100", "Istanbul"),
    ("Vestel", "VESTL.IS", "BIST100", "Istanbul"),
    ("Gubre Fabrikalari", "GUBRF.IS", "BIST100", "Istanbul"),
    ("Alarko Holding", "ALARK.IS", "BIST100", "Istanbul"),
    ("Emlak Konut GYO", "EKGYO.IS", "BIST100", "Istanbul"),
    ("Turk Telekom", "TTKOM.IS", "BIST100", "Istanbul"),
    ("Halkbank", "HALKB.IS", "BIST100", "Istanbul"),
    ("Vakifbank", "VAKBN.IS", "BIST100", "Istanbul"),
    ("Dogan Holding", "DOHOL.IS", "BIST100", "Istanbul"),
    ("Aksa Enerji", "AKSEN.IS", "BIST100", "Istanbul"),
    ("Migros", "MGROS.IS", "BIST100", "Istanbul"),
    ("Coca-Cola Icecek", "CCOLA.IS", "BIST100", "Istanbul"),
    ("Anadolu Efes", "AEFES.IS", "BIST100", "Istanbul"),
    ("Kordsa", "KORDS.IS", "BIST100", "Istanbul"),
    ("Logo Yazilim", "LOGO.IS", "BIST100", "Istanbul"),
    ("Tekfen Holding", "TKFEN.IS", "BIST100", "Istanbul"),
    ("Turk Hava Yollari Kontrolmatik", "KONTR.IS", "BIST100", "Istanbul"),
    ("Otokar", "OTKAR.IS", "BIST100", "Istanbul"),
    ("Enerjisa", "ENJSA.IS", "BIST100", "Istanbul"),
    # ── Prague PX (.PR) ──
    ("CEZ", "CEZ.PR", "PX", "Prague"),
    ("Komercni Banka", "KOMB.PR", "PX", "Prague"),
    ("Moneta Money Bank", "MONET.PR", "PX", "Prague"),
    ("Erste Group (Prague)", "ERBAG.PR", "PX", "Prague"),
    ("Vienna Insurance (Prague)", "VIG.PR", "PX", "Prague"),
    ("Philip Morris CR", "TABAK.PR", "PX", "Prague"),
    ("Kofola", "KOFOL.PR", "PX", "Prague"),
    ("Colt CZ Group", "CZG.PR", "PX", "Prague"),
    ("Gevorkyan", "GEVO.PR", "PX", "Prague"),
    # ── Budapest BUX (.BD) ──
    ("OTP Bank", "OTP.BD", "BUX", "Budapest"),
    ("MOL", "MOL.BD", "BUX", "Budapest"),
    ("Gedeon Richter", "RICHT.BD", "BUX", "Budapest"),
    ("Magyar Telekom", "MTEL.BD", "BUX", "Budapest"),
    ("Opus Global", "OPUS.BD", "BUX", "Budapest"),
    ("Waberer's", "WBERES.BD", "BUX", "Budapest"),
    ("Zwack Unicum", "ZWACK.BD", "BUX", "Budapest"),
    ("Raba", "RABA.BD", "BUX", "Budapest"),
    ("ANY Security Printing", "ANY.BD", "BUX", "Budapest"),
    ("PannErgy", "PANNERGY.BD", "BUX", "Budapest"),
    ("Masterplast", "MASTERPLAST.BD", "BUX", "Budapest"),
    ("Alteo", "ALTEO.BD", "BUX", "Budapest"),
    # ── Baltics (Nasdaq Tallinn/Riga/Vilnius) ──
    ("Tallink Grupp", "TAL1T.TL", "OMXTGI", "Tallinn"),
    ("LHV Group", "LHV1T.TL", "OMXTGI", "Tallinn"),
    ("Enefit Green", "EGR1T.TL", "OMXTGI", "Tallinn"),
    ("Coop Pank", "CPA1T.TL", "OMXTGI", "Tallinn"),
    ("Ignitis Grupe", "IGN1L.VS", "OMXVGI", "Vilnius"),
    ("Siauliu Bankas", "SAB1L.VS", "OMXVGI", "Vilnius"),
    ("Telia Lietuva", "TEL1L.VS", "OMXVGI", "Vilnius"),
    ("Latvijas Gaze", "GZE1R.RG", "OMXRGI", "Riga"),
    # ── Iceland (Nasdaq Iceland .IC) ──
    ("Arion Banki", "ARION.IC", "OMXIPI", "Iceland"),
    ("Iceland Seafood", "ICESEA.IC", "OMXIPI", "Iceland"),
    ("Brim", "BRIM.IC", "OMXIPI", "Iceland"),
    ("Reitir", "REITIR.IC", "OMXIPI", "Iceland"),
]


def _load_seed(seed: Path | None) -> pd.DataFrame:
    cands = [seed] if seed else SEED_CANDIDATES
    for c in cands:
        if c and Path(c).exists():
            df = pd.read_csv(c)
            print(f"  seed: {c}  ({len(df)} rows)")
            return df
    raise SystemExit(
        "  ✗ No seed found. Expected git-tracked europe_all_list.csv at "
        + " or ".join(str(x) for x in SEED_CANDIDATES))


def _validate(tickers: list[str]) -> set[str]:
    """Return the subset of tickers that return data from a 5-day yfinance pull."""
    try:
        import yfinance as yf
    except Exception:
        print("  ⚠ yfinance not installed — skipping validation")
        return set(tickers)
    good = set()
    print(f"  validating {len(tickers)} emerging tickers via yfinance (5d) …")
    try:
        data = yf.download(tickers, period="5d", group_by="ticker",
                           progress=False, threads=True)
    except Exception as e:
        print(f"  ⚠ bulk validation failed ({e}) — keeping all")
        return set(tickers)
    for t in tickers:
        try:
            sub = data[t] if hasattr(data.columns, "levels") else data
            if sub.dropna(how="all").shape[0] > 0:
                good.add(t)
        except Exception:
            pass
    print(f"  {len(good)}/{len(tickers)} emerging tickers valid "
          f"(dropped {len(tickers) - len(good)})")
    return good


def main():
    ap = argparse.ArgumentParser(description="Rebuild data/europe_broad_list.csv")
    ap.add_argument("--seed", type=Path, default=None, help="Override seed CSV path")
    ap.add_argument("--validate", action="store_true",
                    help="Drop emerging tickers that return no yfinance data")
    a = ap.parse_args()

    seed = _load_seed(a.seed)
    seed = seed[["yf_ticker", "name", "index", "exchange"]].copy()

    emerging = pd.DataFrame(
        [(t, n, i, e) for (n, t, i, e) in EMERGING],
        columns=["yf_ticker", "name", "index", "exchange"])

    if a.validate:
        good = _validate(emerging["yf_ticker"].tolist())
        emerging = emerging[emerging["yf_ticker"].isin(good)]

    broad = (pd.concat([seed, emerging], ignore_index=True)
             .drop_duplicates(subset="yf_ticker", keep="first")
             .reset_index(drop=True))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    broad.to_csv(OUT, index=False)

    n_exch = broad["exchange"].nunique()
    print(f"\n  ✓ {OUT}")
    print(f"    {len(broad)} tickers across {n_exch} exchanges "
          f"(seed {len(seed)} + emerging {len(emerging)})")
    top = broad["exchange"].value_counts().head(8)
    for exch, n in top.items():
        print(f"      {exch:<26} {n}")


if __name__ == "__main__":
    main()
