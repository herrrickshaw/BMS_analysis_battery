#!/usr/bin/env python3
"""J-Quants V2 validator — confirm JP panel data against the official JPX source.

Compares DAILY RETURNS (not levels: our panels are yfinance dividend+split
adjusted, J-Quants AdjC is split-adjusted only, so levels always drift by the
dividend factor). A missed split — the documented yfinance JP/KR failure mode —
appears as a one-day return mismatch of tens of percent, which this catches
even on the free plan's delayed window (rolling 2y ending ~12 weeks back).

V2 API (V1 returned 410 Gone as of 2026-07-23): x-api-key header auth,
/equities/bars/daily endpoint, fields AdjC/AdjFactor/Vo.

Credentials (never committed — see feedback_secrets_stay_local):
    env JQUANTS_API_KEY, or a gitignored env file passed via --env-file.

Usage:
    python3 jquants_validator.py --source gapfill.duckdb [--env-file ~/.jquants.env]
    python3 jquants_validator.py --source /path/to/JP.parquet --tickers 7203.T 6758.T
"""
import argparse, datetime, json, os, sys, time

import pandas as pd
import requests

API = "https://api.jquants.com/v2"
RET_TOL = 0.05          # flag a day when |our_ret - jq_ret| > 5pp (split signature)
MAX_FLAG_DAYS = 0       # any flagged day flags the ticker
REQ_SLEEP = 1.0         # free tier is rate-limited; be polite


def load_env_file(path):
    if not path or not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def get_api_key():
    key = os.environ.get("JQUANTS_API_KEY") or os.environ.get("JQUANTS_REFRESH_TOKEN")
    if not key:
        sys.exit("Set JQUANTS_API_KEY (dashboard-issued V2 key) — "
                 "register at https://jpx-jquants.com (free plan is enough).")
    return key


def jq_code(yf_ticker):
    """7203.T -> 7203 (V2 accepts 4- or 5-char codes)."""
    return yf_ticker.split(".")[0]


def fetch_jq_returns(code, api_key, dfrom, dto):
    rows, cursor = [], None
    while True:
        params = {"code": code, "from": dfrom, "to": dto}
        if cursor:
            params["cursor"] = cursor
        for attempt in range(6):
            r = requests.get(f"{API}/equities/bars/daily", params=params,
                             headers={"x-api-key": api_key}, timeout=30)
            if r.status_code != 429:
                break
            time.sleep(15 * (attempt + 1))   # free-plan rate limit: back off hard
        if r.status_code != 200:
            return None
        d = r.json()
        rows += d.get("data", [])
        cursor = d.get("cursor") or d.get("pagination_key")
        if not cursor:
            break
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if "AdjC" not in df or df["AdjC"].isna().all():
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    s = df.set_index("Date")["AdjC"].astype(float).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.pct_change().dropna()


def our_returns(source, ticker):
    if source.endswith(".duckdb"):
        import duckdb
        con = duckdb.connect(source, read_only=True)
        df = con.execute(
            "SELECT Date, Close FROM ohlcv WHERE Symbol=? ORDER BY Date",
            [ticker]).fetchdf()
        con.close()
    else:
        df = pd.read_parquet(source)
        df = df[df["Symbol"] == ticker][["Date", "Close"]]
    if df.empty:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    s = df.set_index("Date")["Close"].astype(float).sort_index()
    # gapfill DB can hold duplicate (Symbol, Date) rows from restart overlap
    s = s[~s.index.duplicated(keep="last")]
    return s.pct_change().dropna()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    help="gapfill.duckdb or a JP parquet panel (Symbol/Date/Close)")
    ap.add_argument("--tickers", nargs="*", help="default: all .T symbols in source")
    ap.add_argument("--env-file", default=os.path.expanduser("~/.jquants.env"))
    ap.add_argument("--out", default="jquants_flags.parquet")
    ap.add_argument("--window-days", type=int, default=365)
    args = ap.parse_args()

    load_env_file(args.env_file)
    api_key = get_api_key()
    # free tier lags ~12 weeks; stop the window there so absence != mismatch
    dto = (datetime.date.today() - datetime.timedelta(weeks=13)).isoformat()
    dfrom = (datetime.date.today()
             - datetime.timedelta(days=args.window_days)).isoformat()

    if args.tickers:
        tickers = args.tickers
    elif args.source.endswith(".duckdb"):
        import duckdb
        con = duckdb.connect(args.source, read_only=True)
        tickers = [r[0] for r in con.execute(
            "SELECT DISTINCT Symbol FROM ohlcv WHERE Symbol LIKE '%.T'").fetchall()]
        con.close()
    else:
        tickers = sorted(pd.read_parquet(args.source, columns=["Symbol"])
                         ["Symbol"].unique())
        tickers = [t for t in tickers if str(t).endswith(".T")]

    print(f"validating {len(tickers)} JP tickers vs J-Quants "
          f"({dfrom} → {dto}, return tol {RET_TOL:.0%})")
    flags, checked, no_jq = [], 0, 0
    for i, t in enumerate(tickers):
        ours = our_returns(args.source, t)
        if ours is None or ours.empty:
            continue
        jq = fetch_jq_returns(jq_code(t), api_key, dfrom, dto)
        time.sleep(REQ_SLEEP)
        if jq is None:
            no_jq += 1
            continue
        joined = pd.concat([ours.rename("ours"), jq.rename("jq")],
                           axis=1, join="inner").dropna()
        if joined.empty:
            continue
        checked += 1
        diff = (joined["ours"] - joined["jq"]).abs()
        bad = joined[diff > RET_TOL]
        for dt, row in bad.iterrows():
            flags.append({"Symbol": t, "Date": dt.date().isoformat(),
                          "our_ret": round(row["ours"], 4),
                          "jq_ret": round(row["jq"], 4)})
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(tickers)}] checked={checked} "
                  f"flags={len(flags)} no_jq_data={no_jq}")

    pd.DataFrame(flags).to_parquet(args.out) if flags else None
    summary = {"checked": checked, "flagged_days": len(flags),
               "flagged_tickers": len({f['Symbol'] for f in flags}),
               "no_jq_data": no_jq, "window": [dfrom, dto]}
    print(json.dumps(summary, indent=1))
    if flags:
        print(f"flags written to {args.out} — investigate before trusting "
              f"those tickers' history (likely missed split/adjustment).")


if __name__ == "__main__":
    main()
