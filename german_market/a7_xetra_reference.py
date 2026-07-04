#!/usr/bin/env python3
"""
a7_xetra_reference.py
=====================
Downloads Xetra and Eurex reference + market data via the Deutsche Börse A7 REST API.

A7 is Deutsche Börse's cloud-based order-by-order market data platform.
You need a valid A7 subscription (free tier available for reference data).
Register and generate your API token at: https://a7.deutsche-boerse.com

A7 markets:
  XETR — Xetra (German equities, ETFs, bonds)
  XEUR — Eurex (derivatives)

A7 data interfaces:
  RDI  — Reference Data Interface (instrument master: ISIN, WKN, segment, tick size…)
  EOBI — Enhanced Order Book Interface (full order book, historical, nanosecond)
  EMDI — Enhanced Market Data Interface (trades, quotes, aggregated)

Requirements: pip install requests pandas

Usage:
  # 1. Set your token
  export A7_TOKEN="your-token-here"

  # 2. Fetch all Xetra reference data for a date
  python3 german_market/a7_xetra_reference.py --rdi --market XETR --date 2025-01-10

  # 3. Fetch OHLCV for a specific ISIN (order-book trades aggregated)
  python3 german_market/a7_xetra_reference.py --eobi --isin DE0008469008 --date 2025-01-10

  # 4. Full Xetra instrument universe for a date
  python3 german_market/a7_xetra_reference.py --universe --date 2025-01-10
"""
import os, sys, json, csv, argparse
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

# ── Config ────────────────────────────────────────────────────────────────────
A7_BASE   = "https://a7.deutsche-boerse.com/api/v1/"
DATA      = Path(__file__).parent.parent / "data"

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_token() -> str:
    token = os.environ.get("A7_TOKEN", "")
    if not token:
        print("ERROR: Set your A7 API token:")
        print("  export A7_TOKEN='your-token-here'")
        print("  Get one at: https://a7.deutsche-boerse.com")
        sys.exit(1)
    return token


def session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
        "User-Agent":    "python-a7-client/1.0",
    })
    return s


# ── A7 REST helpers ───────────────────────────────────────────────────────────
def a7_get(sess: requests.Session, path: str, params: dict = None) -> any:
    url = urljoin(A7_BASE, path.lstrip("/"))
    r = sess.get(url, params=params, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


# ── RDI — Reference Data Interface ────────────────────────────────────────────
def rdi_markets(sess) -> list:
    """List available markets: ['XETR', 'XEUR']"""
    return a7_get(sess, "rdi") or []


def rdi_segments(sess, market: str, date_str: str) -> list:
    """List all market segments for market on date (YYYYMMDD)."""
    return a7_get(sess, f"rdi/{market}/{date_str}") or []


def rdi_instruments(sess, market: str, date_str: str,
                    segment_id: int | str, mode: str = "detailed") -> dict:
    """Get all instruments for a market segment.
    mode: 'reference' | 'keys' | 'detailed'
    Returns dict with 'Securities', 'ProductList', 'MarketSegmentId' etc.
    """
    return a7_get(sess, f"rdi/{market}/{date_str}/{segment_id}",
                  params={"mode": mode}) or {}


def fetch_all_xetra_instruments(sess, date_str: str) -> list[dict]:
    """Walk all Xetra market segments and collect all instruments."""
    segments = rdi_segments(sess, "XETR", date_str)
    print(f"  Xetra market segments on {date_str}: {len(segments)}")

    all_instruments = []
    for i, seg in enumerate(segments):
        seg_id = seg.get("MarketSegmentId") or seg.get("marketSegmentId")
        if not seg_id:
            continue
        detail = rdi_instruments(sess, "XETR", date_str, seg_id, mode="detailed")
        securities = detail.get("Securities") or detail.get("securities") or []
        for s in securities:
            s["MarketSegmentId"] = seg_id
            s["SegmentName"]     = seg.get("MarketSegment") or seg.get("marketSegment", "")
        all_instruments.extend(securities)
        if (i + 1) % 10 == 0 or i == len(segments) - 1:
            print(f"  [{i+1}/{len(segments)}] segments processed, "
                  f"{len(all_instruments):,} instruments so far", flush=True)

    return all_instruments


def flatten_instrument(inst: dict) -> dict:
    """Flatten a Xetra RDI instrument dict to a CSV-ready row."""
    row = {}
    for k, v in inst.items():
        if isinstance(v, (dict, list)):
            # Flatten one level of nested dicts
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    row[f"{k}_{k2}"] = str(v2) if v2 is not None else ""
            else:
                row[k] = json.dumps(v)
        else:
            row[k] = v if v is not None else ""
    return row


# ── EOBI — Enhanced Order Book Interface ─────────────────────────────────────
def eobi_dates(sess, market: str = "XETR") -> list:
    """List available EOBI data dates."""
    return a7_get(sess, f"eobi/{market}") or []


def eobi_instruments(sess, market: str, date_str: str) -> list:
    """List all instrument IDs with EOBI data for the day."""
    return a7_get(sess, f"eobi/{market}/{date_str}") or []


def eobi_trades(sess, market: str, date_str: str, instrument_id: int | str,
                start_time: str = None, end_time: str = None) -> list:
    """Fetch order-book trades for one instrument.
    Returns list of trade events (nanosecond-level).
    start_time/end_time: ISO time strings 'HH:MM:SS'
    """
    params = {}
    if start_time: params["startTime"] = start_time
    if end_time:   params["endTime"]   = end_time
    return a7_get(sess, f"eobi/{market}/{date_str}/{instrument_id}",
                  params=params or None) or []


def eobi_ohlcv(trades: list, resolution: str = "1min") -> list[dict]:
    """Aggregate raw EOBI trades to OHLCV bars.
    trades: list of dicts with 'TransactTime', 'LastPx', 'LastQty'
    resolution: '1min' | '5min' | '1h' | 'day'
    """
    if not trades:
        return []
    try:
        import pandas as pd
        df = pd.DataFrame(trades)
        df["ts"] = pd.to_datetime(df["TransactTime"], errors="coerce", utc=True)
        df["price"] = pd.to_numeric(df.get("LastPx", df.get("lastPx", 0)), errors="coerce")
        df["qty"]   = pd.to_numeric(df.get("LastQty", df.get("lastQty", 0)), errors="coerce")
        df = df.dropna(subset=["ts", "price"]).set_index("ts").sort_index()

        freq_map = {"1min": "1min", "5min": "5min", "1h": "1h", "day": "D"}
        freq = freq_map.get(resolution, "1min")
        ohlcv = df["price"].resample(freq).ohlc()
        ohlcv["volume"] = df["qty"].resample(freq).sum()
        ohlcv["trades"] = df["price"].resample(freq).count()
        return ohlcv.reset_index().to_dict("records")
    except ImportError:
        # Fallback: manual day aggregation
        prices = [t.get("LastPx") or t.get("lastPx", 0) for t in trades]
        qtys   = [t.get("LastQty") or t.get("lastQty", 0) for t in trades]
        return [{
            "open":   prices[0], "high": max(prices), "low": min(prices),
            "close":  prices[-1], "volume": sum(qtys), "trades": len(trades)
        }]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token",   default=None,  help="A7 API token (or set A7_TOKEN env)")
    parser.add_argument("--market",  default="XETR", choices=["XETR","XEUR"], help="Market")
    parser.add_argument("--date",    default=str(date.today() - timedelta(days=1)),
                        help="Date YYYY-MM-DD (default: yesterday)")

    subparsers = parser.add_subparsers(dest="cmd")

    p_rdi = subparsers.add_parser("rdi",  help="Reference data (list markets / segments / instruments)")
    p_rdi.add_argument("--segment", default=None, help="Specific segment ID")
    p_rdi.add_argument("--mode",    default="detailed", choices=["reference","keys","detailed"])
    p_rdi.add_argument("--out",     default=None)

    p_uni = subparsers.add_parser("universe", help="Full Xetra instrument universe for a date")
    p_uni.add_argument("--out",     default=None)

    p_eobi = subparsers.add_parser("eobi", help="Order book / trade data for one instrument")
    p_eobi.add_argument("--instrument-id", required=True, help="A7 numeric instrument ID")
    p_eobi.add_argument("--isin",   default=None,  help="ISIN (for labeling; ID still required)")
    p_eobi.add_argument("--from",   default=None,  dest="from_time", help="Start HH:MM:SS")
    p_eobi.add_argument("--to",     default=None,  dest="to_time",   help="End HH:MM:SS")
    p_eobi.add_argument("--ohlcv",  default="1min", choices=["1min","5min","1h","day"])
    p_eobi.add_argument("--out",    default=None)

    p_dates = subparsers.add_parser("dates", help="List available EOBI dates")

    # Legacy flat flags
    parser.add_argument("--rdi",     action="store_const", const="rdi",      dest="cmd_flag")
    parser.add_argument("--universe",action="store_const", const="universe",  dest="cmd_flag")
    parser.add_argument("--eobi",    action="store_const", const="eobi",      dest="cmd_flag")
    parser.add_argument("--isin",    default=None)
    parser.add_argument("--out",     default=None)

    args = parser.parse_args()
    cmd = args.cmd or getattr(args, "cmd_flag", None)
    token = args.token or os.environ.get("A7_TOKEN", "")
    if not token:
        print("ERROR: Provide --token or export A7_TOKEN='your-token'")
        print("Get token at: https://a7.deutsche-boerse.com")
        sys.exit(1)

    DATA.mkdir(exist_ok=True)
    sess = session(token)
    date_nodash = args.date.replace("-", "")

    # ── List markets ──────────────────────────────────────────────────────────
    if not cmd:
        markets = rdi_markets(sess)
        print(f"Available A7 markets: {markets}")
        return

    # ── RDI: reference data ───────────────────────────────────────────────────
    if cmd == "rdi":
        segment_id = getattr(args, "segment", None)
        mode       = getattr(args, "mode", "detailed")
        out        = getattr(args, "out", None) or args.out

        if segment_id:
            print(f"[A7 RDI] {args.market} segment {segment_id} on {args.date}...")
            data = rdi_instruments(sess, args.market, date_nodash, segment_id, mode)
            securities = data.get("Securities", data.get("securities", [data]))
            print(f"  {len(securities)} instruments")
            for s in securities[:5]:
                print(f"    {json.dumps(s, indent=2)[:200]}")
        else:
            segments = rdi_segments(sess, args.market, date_nodash)
            print(f"[A7 RDI] {args.market} market segments on {args.date}: {len(segments)}")
            for seg in segments[:20]:
                print(f"  {seg}")
            if out:
                with open(out, "w") as f:
                    json.dump(segments, f, indent=2)
                print(f"Saved: {out}")

    # ── Full Xetra universe ───────────────────────────────────────────────────
    elif cmd == "universe":
        out = getattr(args, "out", None) or args.out
        out = Path(out) if out else DATA / f"xetra_universe_{args.date}.csv"
        print(f"[A7 RDI] Building full Xetra instrument universe for {args.date}...")
        instruments = fetch_all_xetra_instruments(sess, date_nodash)
        print(f"\nTotal instruments: {len(instruments):,}")

        if instruments:
            flat = [flatten_instrument(i) for i in instruments]
            all_keys: list[str] = []
            seen = set()
            for row in flat:
                for k in row:
                    if k not in seen:
                        all_keys.append(k); seen.add(k)

            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
                w.writeheader()
                for row in flat:
                    w.writerow({k: row.get(k, "") for k in all_keys})
            print(f"Saved: {out}")

            # Print type breakdown
            from collections import Counter
            types = Counter(i.get("InstrumentType") or i.get("instrumentType", "?")
                            for i in instruments)
            print(f"\nInstrument types: {dict(types.most_common(10))}")

            # Quick merge with our validated universe
            universe_file = DATA / "validated_universe_flat.csv"
            if universe_file.exists():
                isin_map = {}
                for i in instruments:
                    isin = (i.get("ISIN") or i.get("isin") or
                            i.get("SecurityIdentifier") or "")
                    if isin:
                        isin_map[isin] = i

                de_rows = [r for r in csv.DictReader(open(universe_file))
                           if r["market_code"] == "DE"]
                matched = 0
                for r in de_rows:
                    # Match via ISIN (if in validated universe) or ticker
                    sym = r["yf_symbol"].replace(".DE","").replace(".F","")
                    for inst in instruments:
                        mnem = (inst.get("Mnemonic") or inst.get("mnemonic") or
                                inst.get("InstrumentSymbol") or "")
                        if mnem == sym:
                            matched += 1
                            break
                print(f"\nUniverse DE tickers matched to A7 data: "
                      f"{matched}/{len(de_rows)} ({100*matched/max(1,len(de_rows)):.1f}%)")

    # ── EOBI: order book trades ───────────────────────────────────────────────
    elif cmd == "eobi":
        inst_id   = getattr(args, "instrument_id", None)
        from_time = getattr(args, "from_time", None)
        to_time   = getattr(args, "to_time", None)
        ohlcv_res = getattr(args, "ohlcv", "1min")
        out       = getattr(args, "out", None) or args.out

        if not inst_id:
            print("ERROR: provide --instrument-id (numeric A7 ID)")
            print("Hint: get instrument IDs from the 'universe' command RDI data")
            sys.exit(1)

        label = getattr(args, "isin", None) or inst_id
        print(f"[A7 EOBI] {label} on {args.date} ({args.market})...")
        trades = eobi_trades(sess, args.market, date_nodash, inst_id,
                             from_time, to_time)
        print(f"  {len(trades):,} trade events")

        if trades:
            bars = eobi_ohlcv(trades, ohlcv_res)
            print(f"\n{ohlcv_res} OHLCV ({len(bars)} bars):")
            print(f"  {'Time':<22} {'Open':>12} {'High':>12} {'Low':>12} "
                  f"{'Close':>12} {'Volume':>15} {'Trades':>8}")
            print("─" * 95)
            for bar in bars[:20]:
                t = str(bar.get("ts", bar.get("index", "")))
                print(f"  {t:<22} {bar.get('open',''):>12} {bar.get('high',''):>12} "
                      f"{bar.get('low',''):>12} {bar.get('close',''):>12} "
                      f"{bar.get('volume',''):>15} {bar.get('trades',''):>8}")

            out_path = Path(out) if out else DATA / f"eobi_{label}_{args.date}_{ohlcv_res}.csv"
            if bars:
                keys = list(bars[0].keys())
                with open(out_path, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                    w.writeheader(); w.writerows(bars)
                print(f"\nSaved: {out_path}")

    # ── List EOBI dates ───────────────────────────────────────────────────────
    elif cmd == "dates":
        dates = eobi_dates(sess, args.market)
        print(f"[A7 EOBI] Available {args.market} data dates:")
        for d in dates[-20:]:
            print(f"  {d}")


if __name__ == "__main__":
    main()
