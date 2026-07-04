#!/usr/bin/env python3
"""
xetra_pds.py
============
Downloads 1-minute OHLCV data from the Deutsche Börse Xetra Public Data Set (PDS).

NOTE: The bucket was deprecated in 2023. Access now requires:
  1. AWS credentials (free AWS account)
  2. RequestPayer='requester' flag (you pay the egress)
  Cost: ~$0.09/GB. Typical trading day ≈ 50–150 MB total.

Bucket: s3://deutsche-boerse-xetra-pds (eu-central-1)
Format: YYYY-MM-DD/YYYY-MM-DD_BINS_XETR{HH}.csv (one file per UTC hour)

CSV columns:
  ISIN, Mnemonic, SecurityDesc, SecurityType, Currency,
  SecurityID, Date, Time, StartPrice, MaxPrice, MinPrice,
  EndPrice, TradedVolume, NumberOfTrades

Trading hours on Xetra (UTC): 07:00–15:30 (09:00–17:30 CET)
File hours: 07 08 09 10 11 12 13 14 15

Requirements: pip install boto3 pandas

Usage:
  export AWS_ACCESS_KEY_ID=...
  export AWS_SECRET_ACCESS_KEY=...

  # Download one day + compute daily aggregates
  python3 german_market/xetra_pds.py --date 2024-01-10

  # Download a date range
  python3 german_market/xetra_pds.py --start 2024-01-02 --end 2024-01-31

  # Filter to specific ISINs
  python3 german_market/xetra_pds.py --date 2024-01-10 --isins DE0008469008,DE0005140008

  # Merge with our validated universe to add names
  python3 german_market/xetra_pds.py --date 2024-01-10 --with-universe
"""
import os, sys, csv, io, argparse
from datetime import date, timedelta, datetime
from pathlib import Path
from collections import defaultdict

try:
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    from botocore.exceptions import ClientError
except ImportError:
    sys.exit("pip install boto3")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

BUCKET  = "deutsche-boerse-xetra-pds"
REGION  = "eu-central-1"
DATA    = Path(__file__).parent.parent / "data"

# Trading hours on Xetra (UTC hours)
XETRA_HOURS = [7, 8, 9, 10, 11, 12, 13, 14, 15]


# ── S3 client ─────────────────────────────────────────────────────────────────
def s3_client(requester_pays: bool = True):
    """Create S3 client. Tries anonymous first, falls back to requester-pays."""
    session = boto3.Session(
        aws_access_key_id     = os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name           = REGION,
    )
    return session.client("s3", region_name=REGION)


def list_day(client, date_str: str) -> list[str]:
    """List all PDS keys for one day (YYYY-MM-DD)."""
    prefix = f"{date_str}/"
    try:
        resp = client.list_objects_v2(
            Bucket=BUCKET, Prefix=prefix, RequestPayer="requester"
        )
        return [obj["Key"] for obj in resp.get("Contents", [])]
    except ClientError as e:
        if e.response["Error"]["Code"] in ("AccessDenied", "NoSuchBucket"):
            print(f"  S3 access denied for {prefix}: {e}")
            return []
        raise


def download_hour_csv(client, key: str) -> list[dict]:
    """Download one hourly CSV from S3 and parse it."""
    try:
        resp = client.get_object(Bucket=BUCKET, Key=key, RequestPayer="requester")
        body = resp["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(body), delimiter=",")
        return list(reader)
    except ClientError as e:
        print(f"  Failed to fetch {key}: {e}")
        return []


# ── Data processing ───────────────────────────────────────────────────────────
def day_key(date_str: str, hour: int) -> str:
    return f"{date_str}/{date_str}_BINS_XETR{hour:02d}.csv"


def parse_float(v) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if v and str(v).strip() else None
    except ValueError:
        return None


def aggregate_day(records: list[dict], isin_filter: set = None) -> dict[str, dict]:
    """
    Aggregate 1-minute bars to daily OHLCV per ISIN.
    Returns {isin: {open, high, low, close, volume, trades, mnemonic, desc, currency}}
    """
    agg: dict[str, dict] = defaultdict(lambda: {
        "open": None, "high": None, "low": None, "close": None,
        "volume": 0.0, "trades": 0,
        "mnemonic": "", "desc": "", "currency": "", "security_type": ""
    })

    for r in records:
        isin = r.get("ISIN", "").strip()
        if not isin or (isin_filter and isin not in isin_filter):
            continue

        a = agg[isin]
        a["mnemonic"]      = r.get("Mnemonic", "")
        a["desc"]          = r.get("SecurityDesc", "")
        a["currency"]      = r.get("Currency", "")
        a["security_type"] = r.get("SecurityType", "")

        start = parse_float(r.get("StartPrice"))
        high  = parse_float(r.get("MaxPrice"))
        low   = parse_float(r.get("MinPrice"))
        end   = parse_float(r.get("EndPrice"))
        vol   = parse_float(r.get("TradedVolume")) or 0.0
        n_tr  = int(float(r.get("NumberOfTrades") or 0))

        if start is not None and a["open"] is None:
            a["open"] = start
        if high is not None:
            a["high"] = max(a["high"], high) if a["high"] is not None else high
        if low is not None:
            a["low"] = min(a["low"], low) if a["low"] is not None else low
        if end is not None:
            a["close"] = end
        a["volume"] += vol
        a["trades"] += n_tr

    return dict(agg)


def aggregate_1min(records: list[dict], isin_filter: set = None) -> list[dict]:
    """Return 1-minute OHLCV records filtered to isin_filter (or all if None)."""
    out = []
    for r in records:
        isin = r.get("ISIN", "").strip()
        if isin_filter and isin not in isin_filter:
            continue
        out.append({
            "isin":          isin,
            "mnemonic":      r.get("Mnemonic", ""),
            "date":          r.get("Date", ""),
            "time":          r.get("Time", ""),
            "open":          parse_float(r.get("StartPrice")),
            "high":          parse_float(r.get("MaxPrice")),
            "low":           parse_float(r.get("MinPrice")),
            "close":         parse_float(r.get("EndPrice")),
            "volume":        parse_float(r.get("TradedVolume")),
            "trades":        int(float(r.get("NumberOfTrades") or 0)),
            "currency":      r.get("Currency", ""),
            "security_type": r.get("SecurityType", ""),
        })
    return out


def market_stats(daily: dict[str, dict]) -> dict:
    """Compute market-wide stats from daily aggregates."""
    prices  = [v["close"] for v in daily.values() if v.get("close")]
    volumes = [v["volume"] for v in daily.values() if v.get("volume")]
    advancers = sum(1 for v in daily.values()
                    if v.get("close") and v.get("open") and v["close"] > v["open"])
    decliners = sum(1 for v in daily.values()
                    if v.get("close") and v.get("open") and v["close"] < v["open"])
    return {
        "total_instruments": len(daily),
        "total_volume":      sum(volumes),
        "total_turnover":    sum(v["volume"] * v["close"] for v in daily.values()
                                 if v.get("volume") and v.get("close")),
        "total_trades":      sum(v["trades"] for v in daily.values()),
        "advancers":         advancers,
        "decliners":         decliners,
        "unchanged":         len(daily) - advancers - decliners,
        "avg_price":         sum(prices) / len(prices) if prices else 0,
        "top_by_volume":     sorted(daily.items(),
                                    key=lambda x: x[1]["volume"], reverse=True)[:10],
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    default=str(date.today() - timedelta(days=3)),
                        help="Single date YYYY-MM-DD")
    parser.add_argument("--start",   default=None, help="Start date for range")
    parser.add_argument("--end",     default=None, help="End date for range")
    parser.add_argument("--isins",   default=None,
                        help="Comma-separated ISIN filter (e.g. DE0008469008,DE0005140008)")
    parser.add_argument("--with-universe", action="store_true",
                        help="Merge with validated_universe_flat.csv")
    parser.add_argument("--intraday", action="store_true",
                        help="Save 1-minute bars instead of daily aggregates")
    parser.add_argument("--out",     default=None)
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    client = s3_client()

    isin_filter = None
    if args.isins:
        isin_filter = set(i.strip() for i in args.isins.split(","))
        print(f"ISIN filter: {isin_filter}")

    # Load universe for ISIN lookup if requested
    universe_isin: dict[str, dict] = {}
    if args.with_universe:
        uf = DATA / "validated_universe_flat.csv"
        if not uf.exists():
            uf = DATA / "global_universe_flat.csv"
        if uf.exists():
            for row in csv.DictReader(open(uf)):
                if row["market_code"] == "DE":
                    isin = row.get("isin", "")
                    if isin:
                        universe_isin[isin] = row

    # Build date list
    dates: list[str] = []
    if args.start and args.end:
        d = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_d = datetime.strptime(args.end, "%Y-%m-%d").date()
        while d <= end_d:
            if d.weekday() < 5:  # skip weekends
                dates.append(str(d))
            d += timedelta(days=1)
    else:
        dates = [args.date]

    all_daily: list[dict] = []
    all_1min:  list[dict] = []

    for date_str in dates:
        print(f"\n[Xetra PDS] Downloading {date_str}...")
        all_records: list[dict] = []

        for hour in XETRA_HOURS:
            key = day_key(date_str, hour)
            records = download_hour_csv(client, key)
            if records:
                all_records.extend(records)
                print(f"  {hour:02d}:00  {len(records):>6,} records", flush=True)

        if not all_records:
            print(f"  No data for {date_str}")
            continue

        print(f"  Total: {len(all_records):,} 1-minute records")

        if args.intraday:
            bars_1min = aggregate_1min(all_records, isin_filter)
            for row in bars_1min:
                row["date_label"] = date_str
            all_1min.extend(bars_1min)
        else:
            daily = aggregate_day(all_records, isin_filter)
            stats = market_stats(daily)
            print(f"\n  ── {date_str} Market Summary ─────────────────")
            print(f"  Instruments traded : {stats['total_instruments']:,}")
            print(f"  Total volume (sh.) : {stats['total_volume']:,.0f}")
            print(f"  Total trades       : {stats['total_trades']:,}")
            print(f"  Advancers / Declin.: {stats['advancers']} / {stats['decliners']}")
            print(f"\n  Top 10 by volume:")
            print(f"  {'ISIN':<14} {'Mnemonic':<8} {'Close':>10} {'Volume':>15} {'Trades':>8}")
            print("  " + "─" * 60)
            for isin, d in stats["top_by_volume"]:
                info = d
                uni  = universe_isin.get(isin, {})
                mnem = info.get("mnemonic") or uni.get("exchange", "")[:8]
                print(f"  {isin:<14} {mnem:<8} "
                      f"{info.get('close', 0):>10.2f} "
                      f"{info.get('volume', 0):>15,.0f} "
                      f"{info.get('trades', 0):>8,}")

            for isin, d in daily.items():
                row = {"date": date_str, "isin": isin, **d}
                if isin in universe_isin:
                    row["yf_symbol"]    = universe_isin[isin].get("yf_symbol", "")
                    row["market_name"]  = universe_isin[isin].get("market_name", "")
                all_daily.append(row)

    # Save output
    if all_daily:
        out = Path(args.out) if args.out else DATA / "xetra_daily_ohlcv.csv"
        keys = list(all_daily[0].keys())
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader(); w.writerows(all_daily)
        print(f"\nSaved {len(all_daily):,} daily OHLCV rows → {out}")

    if all_1min:
        out = Path(args.out) if args.out else DATA / "xetra_1min_ohlcv.csv"
        keys = list(all_1min[0].keys())
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader(); w.writerows(all_1min)
        print(f"\nSaved {len(all_1min):,} 1-minute bars → {out}")


if __name__ == "__main__":
    main()
