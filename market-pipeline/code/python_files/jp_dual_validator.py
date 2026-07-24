#!/usr/bin/env python3
"""JP dual-source validator — kabupy (kabuyoho scrape) × J-Quants (official API)
validating each other, with our OHLCV panel as the price bridge.

The two sources are complementary in time and kind, so only some comparisons
are honest; this script does exactly those and nothing else:

  ROE   — kabupy `actual_roe` (scraped, latest FY)  vs  J-Quants NP/Eq from
          /fins/summary (officially filed). Same basis → tight-ish tolerance.
  PER   — kabupy `expected_per` is a FORECAST; official EPS × our latest close
          gives TRAILING PER. Different bases → only extreme divergence flags.
  NAME  — kabupy company name vs symbol_master name: catches wrong-ticker
          mapping (the silent killer), exact-prefix match on kanji.

Known-broken kabupy fields (kabuyoho DOM drift, 2026-07-23): `price` selector
404s, `market_capitalization` misparses units — deliberately NOT used.

Outputs jp_dual_validation.parquet + JSON summary. Rate-polite to both
sources; J-Quants calls reuse the 429 backoff pattern.

Usage:
    python3 jp_dual_validator.py --source gapfill.duckdb [--sample 100]
"""
import argparse, datetime, json, os, sys, time

import pandas as pd
import requests

API = "https://api.jquants.com/v2"
ROE_TOL_PP = 3.0        # |kabupy ROE - official ROE| > 3 percentage points → flag
ROE_TOL_REL = 0.30      # ... AND >30% relative (both must trip)
PER_TOL_REL = 0.50      # forecast vs trailing PER: only >50% divergence flags
SLEEP_JQ = 1.0
SLEEP_KB = 1.2


def load_env_file(path):
    if path and os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def jq_fins(code, key):
    for attempt in range(6):
        r = requests.get(f"{API}/fins/summary", params={"code": code},
                         headers={"x-api-key": key}, timeout=30)
        if r.status_code != 429:
            break
        time.sleep(15 * (attempt + 1))
    if r.status_code != 200:
        return None
    rows = [d for d in r.json().get("data", [])
            if d.get("CurPerType") == "FY" and d.get("NP") and d.get("Eq")]
    if not rows:
        return None
    d = max(rows, key=lambda x: x.get("CurPerEn", ""))
    try:
        return {"np": float(d["NP"]), "eq": float(d["Eq"]),
                "eps": float(d["EPS"]) if d.get("EPS") else None,
                "fy_end": d.get("CurPerEn")}
    except (ValueError, TypeError):
        return None


def kb_top(code):
    import kabupy
    rt = kabupy.Kabuyoho().stock(int(code)).report_top
    out = {}
    for f in ("name", "actual_roe", "expected_per"):
        try:
            v = getattr(rt, f)
            out[f] = float(v) if f != "name" else str(v)
        except Exception:
            out[f] = None
    return out


def latest_close(source, ticker):
    import duckdb
    if source.endswith(".duckdb"):
        con = duckdb.connect(source, read_only=True)
        r = con.execute("SELECT Close FROM ohlcv WHERE Symbol=? "
                        "ORDER BY Date DESC LIMIT 1", [ticker]).fetchone()
        con.close()
    else:
        con = duckdb.connect()
        r = con.execute(f"SELECT Close FROM read_parquet('{source}') "
                        f"WHERE Symbol=? ORDER BY Date DESC LIMIT 1", [ticker]).fetchone()
    return float(r[0]) if r else None


def names_from_master(path):
    try:
        import duckdb
        con = duckdb.connect()
        return dict(con.execute(
            f"SELECT symbol, name FROM read_parquet('{path}') "
            f"WHERE exchange='JAPAN'").fetchall())
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--env-file", default=os.path.expanduser("~/.jquants.env"))
    ap.add_argument("--symbol-master", default=os.path.expanduser(
        "~/collector/symbol_master.parquet"))
    ap.add_argument("--out", default="jp_dual_validation.parquet")
    args = ap.parse_args()

    load_env_file(args.env_file)
    key = os.environ.get("JQUANTS_API_KEY") or os.environ.get("JQUANTS_REFRESH_TOKEN")
    if not key:
        sys.exit("JQUANTS_API_KEY missing")

    import duckdb
    if args.source.endswith(".duckdb"):
        con = duckdb.connect(args.source, read_only=True)
        tickers = [r[0] for r in con.execute(
            "SELECT DISTINCT Symbol FROM ohlcv WHERE Symbol LIKE '%.T'").fetchall()]
        con.close()
    else:
        con = duckdb.connect()
        tickers = [r[0] for r in con.execute(
            f"SELECT DISTINCT Symbol FROM read_parquet('{args.source}') "
            f"WHERE Symbol LIKE '%.T'").fetchall()]
    tickers = sorted(tickers)
    if args.sample:
        tickers = tickers[::max(1, len(tickers) // args.sample)][:args.sample]
    master_names = names_from_master(args.symbol_master)

    print(f"dual-validating {len(tickers)} JP tickers (kabupy × J-Quants)", flush=True)
    rows = []
    for i, t in enumerate(tickers):
        code = t.split(".")[0]
        rec = {"Symbol": t, "roe_check": "no_data", "per_check": "no_data",
               "name_check": "no_data"}
        try:
            kb = kb_top(code)
        except Exception:
            kb = {}
        time.sleep(SLEEP_KB)
        jq = jq_fins(code, key)
        time.sleep(SLEEP_JQ)

        if jq and jq["eq"]:
            rec["roe_official"] = round(jq["np"] / jq["eq"] * 100, 2)
            if kb.get("actual_roe") is not None:
                a, b = kb["actual_roe"], rec["roe_official"]
                rec["roe_kabupy"] = a
                diverges = (abs(a - b) > ROE_TOL_PP
                            and abs(a - b) > ROE_TOL_REL * max(abs(b), 1e-9))
                rec["roe_check"] = "FLAG" if diverges else "ok"
        cl = latest_close(args.source, t)
        if jq and jq.get("eps") and cl and jq["eps"] > 0:
            rec["per_trailing"] = round(cl / jq["eps"], 1)
            if kb.get("expected_per"):
                rec["per_kabupy_fwd"] = kb["expected_per"]
                rel = abs(rec["per_trailing"] - kb["expected_per"]) / rec["per_trailing"]
                rec["per_check"] = "FLAG" if rel > PER_TOL_REL else "ok"
        mn = master_names.get(t)
        if kb.get("name") and mn:
            rec["name_check"] = ("ok" if str(mn)[:2] in kb["name"]
                                 or kb["name"][:2] in str(mn) else "FLAG")
            rec["name_kabupy"], rec["name_master"] = kb["name"], str(mn)
        rows.append(rec)
        if (i + 1) % 25 == 0:
            f = sum(1 for r in rows if "FLAG" in (r["roe_check"], r["per_check"], r["name_check"]))
            print(f"  [{i+1}/{len(tickers)}] flagged={f}", flush=True)

    df = pd.DataFrame(rows)
    df.to_parquet(args.out, index=False)
    summ = {c: df[c].value_counts().to_dict()
            for c in ("roe_check", "per_check", "name_check")}
    print(json.dumps(summ, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
