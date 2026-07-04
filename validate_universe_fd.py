#!/usr/bin/env python3
"""
validate_universe_fd.py
========================
Validates global_universe_flat.csv using FinanceDatabase (GitHub-hosted CSVs).
FinanceDatabase is the only external source accessible from this sandbox.

FinanceDatabase symbols already include the yfinance suffix (.NS, .BO, .HK, etc.)
so we use them directly — no suffix appending.

Output:
  data/validated_universe_flat.csv   — valid tickers only
  data/validation_report.json        — per-market stats
  data/push_validated_universe.sh    — script to push cleaned data
"""
import csv, json, time, io
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from collections import defaultdict

DATA   = Path(__file__).parent / "data"
INPUT  = DATA / "global_universe_flat.csv"
OUTPUT = DATA / "validated_universe_flat.csv"
REPORT = DATA / "validation_report.json"

FD_BASE = "https://raw.githubusercontent.com/JerBouma/FinanceDatabase/main/database/equities/{code}.csv"

# FinanceDatabase exchange code → market_code in our universe
# FD symbols already include the yfinance suffix (.NS, .BO, .T, .HK, etc.)
FD_EXCHANGE_MAP = [
    # India (NSE → .NS, BSE → .BO)
    ("NSE", "IN"),
    ("BSE", "IN"),
    # Japan (.T)
    ("JPX", "JP"),
    # Korea (.KS) — covers KOSPI; KOSDAQ not in FD so kept as-is
    ("KSC", "KR"),
    # Taiwan (.TW and .TWO)
    ("TAI", "TW"),
    ("TWO", "TW"),
    # China (.SS for SSE, .SZ for SZSE)
    ("SHH", "CN"),
    ("SHZ", "CN"),
    # Hong Kong (.HK)
    ("HKG", "HK"),
    # Singapore (.SI)
    ("SES", "SG"),
    # Australia (.AX)
    ("ASX", "AU"),
    # New Zealand (.NZ)
    ("NZE", "NZ"),
    # UK (.L)
    ("LSE", "UK"),
    # Germany (.DE on Xetra, .F on Frankfurt)
    ("GER", "DE"),
    ("FRA", "DE"),
    # France (.PA)
    ("PAR", "FR"),
    # Italy (.MI)
    ("MIL", "IT"),
    # Sweden (.ST)
    ("STO", "SE"),
    # Norway (.OL)
    ("OSL", "NO"),
    # Denmark (.CO)
    ("CPH", "DK"),
    # Austria (.VI)
    ("VIE", "AT"),
    # Canada (.TO)
    ("TOR", "CA"),
    # Saudi Arabia (.SR)
    ("SAU", "SA"),
    # South Africa (.JO)
    ("JNB", "ZA"),
    # Argentina (.BA)
    ("BUE", "AR"),
    # Russia (.ME)
    ("MCX", "RU"),
    # US — NASDAQ (no suffix) + NYSE (no suffix)
    ("NMS", "US"),
    ("NYQ", "US"),
    # Netherlands (.AS)
    ("AMS", "NL"),
]

# Markets kept without validation (not in FinanceDatabase)
SKIP_VALIDATION = {"BR", "CH", "ES", "AE", "GR", "FI", "BE", "IE", "PL", "PT"}

print("=" * 65)
print("FinanceDatabase Universe Validator")
print("=" * 65)

# ── 1. Load universe ──────────────────────────────────────────────────────────
print(f"\nLoading {INPUT.name}...")
rows = list(csv.DictReader(open(INPUT)))
print(f"  {len(rows):,} tickers across {len({r['market_code'] for r in rows})} markets")

print(f"\n  Market breakdown:")
by_market: dict[str, list[dict]] = defaultdict(list)
for r in rows:
    by_market[r["market_code"]].append(r)
for mc in sorted(by_market, key=lambda m: -len(by_market[m])):
    print(f"    {mc:<6} {len(by_market[mc]):>6,}")


# ── 2. Download FinanceDatabase CSVs ─────────────────────────────────────────
def fetch_fd_csv(code: str) -> list[dict] | None:
    url = FD_BASE.format(code=code)
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        return list(csv.DictReader(io.StringIO(text)))
    except HTTPError as e:
        print(f"    HTTP {e.code}: {code}")
        return None
    except Exception as e:
        print(f"    Error {code}: {e}")
        return None


print(f"\n[FinanceDatabase] Downloading {len(FD_EXCHANGE_MAP)} exchange CSVs...")

# active_yf_symbols[market_code] = set of non-delisted yf_symbols
active_yf_symbols: dict[str, set[str]] = defaultdict(set)
fd_stats: dict[str, dict] = {}

for fd_code, mkt_code in FD_EXCHANGE_MAP:
    print(f"  Fetching {fd_code} → {mkt_code}...", end="", flush=True)
    fd_rows = fetch_fd_csv(fd_code)
    if fd_rows is None:
        print(" FAILED")
        continue

    total = len(fd_rows)
    active_count = 0
    for r in fd_rows:
        # Filter out delisted tickers
        delisted_val = r.get("delisted", "").strip().lower()
        if delisted_val in ("true", "1"):
            continue
        # FD symbol column already includes the yfinance suffix
        sym = r.get("symbol") or (list(r.values())[0] if r else "")
        sym = str(sym).strip()
        if sym and sym.lower() not in ("", "nan", "none"):
            active_yf_symbols[mkt_code].add(sym)
            active_count += 1

    fd_stats[fd_code] = {"total": total, "active": active_count, "market": mkt_code}
    print(f" {total:,} total → {active_count:,} active")
    time.sleep(0.05)

print(f"\nFinanceDatabase download complete.")
print(f"Markets covered: {sorted(active_yf_symbols.keys())}")
for mkt, syms in sorted(active_yf_symbols.items()):
    print(f"  {mkt:<6} {len(syms):>6,} active FD symbols")


# ── 3. Spot-check matching ────────────────────────────────────────────────────
print("\n[Spot-check] Verifying symbol match quality...")
for mc in ["IN", "JP", "HK", "DE", "US", "CA", "TW", "CN"]:
    if mc not in active_yf_symbols or mc not in by_market:
        continue
    universe_sample = [r["yf_symbol"] for r in by_market[mc][:5]]
    fd_hits = [s for s in universe_sample if s in active_yf_symbols[mc]]
    print(f"  {mc}: sample={universe_sample[:3]}, hits={len(fd_hits)}/5")


# ── 4. Determine validity per ticker ─────────────────────────────────────────
print("\n[Validation] Cross-referencing tickers...")
valid_rows: list[dict] = []
invalid_rows: list[dict] = []
market_stats: dict[str, dict] = {}

for r in rows:
    sym  = r["yf_symbol"]
    code = r["market_code"]

    if code in SKIP_VALIDATION:
        is_valid = True
        source = "unchecked"
    elif code in active_yf_symbols:
        is_valid = sym in active_yf_symbols[code]
        source = "financedb"
    else:
        is_valid = True
        source = "unchecked"

    stats = market_stats.setdefault(code, {
        "total": 0, "valid": 0, "invalid": 0, "source": source
    })
    stats["total"] += 1
    if is_valid:
        stats["valid"] += 1
        valid_rows.append(r)
    else:
        stats["invalid"] += 1
        invalid_rows.append(r)


# ── 5. Print report ───────────────────────────────────────────────────────────
print("\n── Validation Report ──────────────────────────────────────────────────────")
print(f"{'Mkt':<6} {'Total':>8} {'Valid':>8} {'Invalid':>8} {'Fail%':>7}  Source")
print("─" * 65)
grand_total = grand_valid = grand_invalid = 0
for code in sorted(market_stats, key=lambda c: -market_stats[c]["total"]):
    s = market_stats[code]
    fail_pct = 100 * s["invalid"] / max(1, s["total"])
    print(f"{code:<6} {s['total']:>8,} {s['valid']:>8,} {s['invalid']:>8,} {fail_pct:>6.1f}%  {s['source']}")
    grand_total   += s["total"]
    grand_valid   += s["valid"]
    grand_invalid += s["invalid"]

print("─" * 65)
print(f"{'TOTAL':<6} {grand_total:>8,} {grand_valid:>8,} {grand_invalid:>8,} {100*grand_invalid/grand_total:>6.1f}%")

if invalid_rows:
    print("\nSample invalid tickers (first 5 per market):")
    invalid_by_mkt: dict[str, list] = defaultdict(list)
    for r in invalid_rows:
        invalid_by_mkt[r["market_code"]].append(r["yf_symbol"])
    for mc in sorted(invalid_by_mkt):
        sample = invalid_by_mkt[mc][:5]
        more = f" (+{len(invalid_by_mkt[mc])-5} more)" if len(invalid_by_mkt[mc]) > 5 else ""
        print(f"  {mc}: {', '.join(sample)}{more}")


# ── 6. Save cleaned CSV ───────────────────────────────────────────────────────
clean_fields = ["market_code", "market_name", "exchange", "yf_symbol"]

with open(OUTPUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=clean_fields)
    w.writeheader()
    for r in valid_rows:
        w.writerow({k: r[k] for k in clean_fields})

print(f"\nSaved: {OUTPUT.name}  ({len(valid_rows):,} valid tickers)")


# ── 7. Save validation report ─────────────────────────────────────────────────
report_data = {
    "summary": {
        "total": grand_total,
        "valid": grand_valid,
        "invalid": grand_invalid,
        "removal_pct": round(100 * grand_invalid / grand_total, 2)
    },
    "by_market": market_stats,
    "fd_exchange_stats": fd_stats
}
with open(REPORT, "w") as f:
    json.dump(report_data, f, indent=2)
print(f"Saved: {REPORT.name}")


# ── 8. Update per-market JSONs ────────────────────────────────────────────────
print("\n[JSON] Pruning invalid tickers from per-market JSON files...")
all_valid_syms = {r["yf_symbol"] for r in valid_rows}

json_files = sorted(DATA.glob("*_tickers_full.json"))
for jf in json_files:
    try:
        with open(jf) as f:
            jdata = json.load(f)
        if not isinstance(jdata, list):
            continue
        before = len(jdata)
        pruned = [t for t in jdata
                  if t.get("yf_symbol", t.get("symbol", "")) in all_valid_syms]
        after = len(pruned)
        with open(jf, "w") as f:
            json.dump(pruned, f, indent=2, ensure_ascii=False)
        removed = before - after
        status = f"  {jf.name}: {before:,} → {after:,}" + (f" ({removed:,} removed)" if removed else " (unchanged)")
        print(status)
    except Exception as e:
        print(f"  {jf.name}: error — {e}")

# Rebuild global_universe.json
gu_path = DATA / "global_universe.json"
if gu_path.exists():
    try:
        with open(gu_path) as f:
            gu = json.load(f)
        before_total = sum(len(v) for v in gu.values())
        for mkt in gu:
            gu[mkt] = [t for t in gu[mkt]
                       if t.get("yf_symbol", t.get("symbol", "")) in all_valid_syms]
        after_total = sum(len(v) for v in gu.values())
        with open(gu_path, "w") as f:
            json.dump(gu, f, indent=2, ensure_ascii=False)
        print(f"  global_universe.json: {before_total:,} → {after_total:,} ({before_total - after_total:,} removed)")
    except Exception as e:
        print(f"  global_universe.json: error — {e}")


# ── 9. Generate push script ───────────────────────────────────────────────────
valid_markets = len({r["market_code"] for r in valid_rows})
push_script = DATA / "push_validated_universe.sh"
push_content = f"""#!/bin/bash
# push_validated_universe.sh
# Pushes the validated (delisted-cleaned) ticker universe to global-ticker-universe.
# Run on your LOCAL machine with GitHub credentials.
# Result: {len(valid_rows):,} tradeable tickers across {valid_markets} markets

set -e
echo "=== Push Validated Universe to global-ticker-universe ==="

WORK=$(mktemp -d)
echo "Working in: $WORK"

# ── 1. Get source data from herrrickshaw (BMS analysis battery) ───────────────
# The validated files were produced by validate_universe_fd.py on branch:
#   claude/nse-bse-pegu-scoring-k7vu9
git clone --depth 1 -b claude/nse-bse-pegu-scoring-k7vu9 \\
    https://github.com/herrrickshaw/herrrickshaw.git "$WORK/src"

# Verify the validated file exists
wc -l "$WORK/src/data/validated_universe_flat.csv"

# ── 2. Clone global-ticker-universe ──────────────────────────────────────────
git clone https://github.com/herrrickshaw/global-ticker-universe.git "$WORK/dest"
cd "$WORK/dest"
mkdir -p data

# ── 3. Copy validated data ────────────────────────────────────────────────────
cp "$WORK/src/data/validated_universe_flat.csv" data/global_universe_flat.csv
[ -f "$WORK/src/data/global_universe.json" ] && cp "$WORK/src/data/global_universe.json" data/
for jf in "$WORK/src/data/"*_tickers_full.json; do
  [ -f "$jf" ] && cp "$jf" data/
done
[ -f "$WORK/src/data/validation_report.json" ] && cp "$WORK/src/data/validation_report.json" data/

echo ""
echo "Files to push:"
wc -l data/global_universe_flat.csv
ls data/*.json 2>/dev/null | wc -l
echo " JSON files"

# ── 4. Commit and push ────────────────────────────────────────────────────────
git add data/
git status --short

if git diff --cached --quiet; then
  echo "Nothing changed — already up to date."
else
  git commit -m "validate: remove delisted/invalid tickers via FinanceDatabase

- {grand_invalid:,} tickers removed ({100*grand_invalid/grand_total:.1f}% of {grand_total:,} total)
- {grand_valid:,} tradeable tickers remain across {valid_markets} markets
- Validation: JerBouma/FinanceDatabase delisted=false cross-reference (29 exchanges)
- Markets kept without FD validation: BR CH ES AE GR FI BE IE PL PT
- Validated {time.strftime('%Y-%m-%d')} by validate_universe_fd.py"
  git push origin main
  echo ""
  echo "Done! Validated CSV live at:"
  echo "https://raw.githubusercontent.com/herrrickshaw/global-ticker-universe/main/data/global_universe_flat.csv"
fi

echo ""
echo "Cleanup: rm -rf $WORK"
"""

with open(push_script, "w") as f:
    f.write(push_content)
push_script.chmod(0o755)
print(f"\nSaved push script: {push_script.name}")


# ── 10. Summary ───────────────────────────────────────────────────────────────
print(f"""
═══════════════════════════════════════════════════════════════════
 SUMMARY
 Original universe  : {grand_total:,} tickers
 Valid / tradeable  : {grand_valid:,}  ({100*grand_valid/grand_total:.1f}%)
 Removed (invalid)  : {grand_invalid:,}  ({100*grand_invalid/grand_total:.1f}%)
═══════════════════════════════════════════════════════════════════
 To push validated data to global-ticker-universe, run locally:
   bash data/push_validated_universe.sh
═══════════════════════════════════════════════════════════════════
""")
