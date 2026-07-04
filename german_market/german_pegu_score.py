#!/usr/bin/env python3
"""
german_pegu_score.py
====================
Builds a PEGU-equivalent score for German stocks tradeable on Eurex,
mirroring the India PEGU methodology (Darvas + Piotroski + Coffee Can).

German PEGU components:
  Ecosystem Score   (0-40)  — derivative types listed: SSF, SSO, TRF, Div Future
  Coverage Score    (0-30)  — number of distinct Eurex product codes (depth proxy)
  Suite Bonus       (0-20)  — full/near-full derivative suite (institutional grade)
  Universe Bonus    (0-10)  — present in validated global universe (.DE ticker)

Darvas equivalent  : OPTIONABLE_FUTURE if has SSO+SSF; FUTURES_ONLY; etc.
Piotroski equiv    : derivative ecosystem depth mapped to 0-9
Coffee Can equiv   : PASS if >= 3 derivative types, FAIL otherwise

Output: data/german_pegu_scored.csv, data/eurex_pegu_all_europe.csv
"""
import urllib.request, csv, io
from collections import defaultdict, Counter
from pathlib import Path

BASE = "https://raw.githubusercontent.com/herrrickshaw/BMS_analysis_battery/eb8a6714172d430aaa62b7d40d77443464801217/data"

COUNTRY_MAP = {
    'DE': 'Germany', 'FR': 'France', 'NL': 'Netherlands', 'CH': 'Switzerland',
    'IT': 'Italy', 'ES': 'Spain', 'BE': 'Belgium', 'AT': 'Austria',
    'SE': 'Sweden', 'FI': 'Finland', 'DK': 'Denmark', 'IE': 'Ireland',
    'LU': 'Luxembourg', 'GB': 'UK', 'JE': 'UK', 'US': 'US', 'NO': 'Norway',
}

SINGLE_STOCK_TYPES = {
    'SINGLE STOCK FUTURES', 'SINGLE STOCK OPTIONS',
    'EQUITY TOTAL RETURN FUTURES', 'SINGLE STOCK DIVIDEND FUTURES',
}

# Key: for SSO (options), ProductISIN = actual underlying ISIN -> reliable country detection
# For SSF/TRF, Eurex assigns its own DE-prefixed ISIN regardless of underlying country
SSO_TYPE = 'SINGLE STOCK OPTIONS'

# Known DAX 40 constituents (Eurex name fragments, uppercase)
DAX40_NAMES = {
    'ADIDAS', 'AIRBUS', 'ALLIANZ', 'BASF', 'BAYER', 'BEIERSDORF',
    'BMW', 'BRENNTAG', 'COMMERZBANK', 'CONTINENTAL', 'COVESTRO',
    'DAIMLER TRUCK', 'DEUTSCHE BANK', 'DEUTSCHE BOERSE', 'DEUTSCHE POST',
    'DEUTSCHE TELEKOM', 'E.ON', 'FRESENIUS MEDICAL', 'FRESENIUS SE',
    'FRESENIUS', 'HANNOVER RE', 'HANNOVER RUECK', 'HEIDELBERG MATERIALS',
    'HEIDELBERGCEMENT', 'HENKEL', 'INFINEON', 'MERCEDES-BENZ',
    'MERCEDES BENZ', 'MERCK KGAA', 'MERCK', 'MTU AERO', 'MUENCHENER',
    'MUNICH RE', 'MUENCHEN RE', 'PUMA', 'QIAGEN', 'RHEINMETALL',
    'RWE', 'SAP', 'SARTORIUS', 'SIEMENS ENERGY', 'SIEMENS HEALTHINEERS',
    'SIEMENS', 'SYMRISE', 'VOLKSWAGEN', 'VONOVIA', 'ZALANDO',
    'PORSCHE', 'DELIVERY HERO',
}


def fetch_csv(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode('utf-8'))))


def extract_underlying(name):
    """Strip derivative prefix/suffix to get underlying stock name."""
    name = name.strip()
    for prefix in ['FUT ON ', 'FUT.ON ', 'OPT ON ', 'OPT E ON ', 'TRF ON ', 'FUTURE ON ']:
        if name.upper().startswith(prefix):
            return name[len(prefix):].strip()
    for suffix in [' DIVIDEND FUTURE', ' DIVIDEND OPTION']:
        if name.upper().endswith(suffix):
            return name[:-len(suffix)].strip()
    return name


def is_dax40(underlying_name):
    u = underlying_name.upper()
    return any(d in u for d in DAX40_NAMES)


def pegu_score(rec):
    types = sum([rec['has_ssf'], rec['has_sso'], rec['has_trf'], rec['has_div']])
    n_codes = rec['n_codes']
    eco   = types * 10                              # 0-40
    cov   = {0:0,1:8,2:15,3:20,4:25,5:28}.get(min(n_codes,5), 30)  # 0-30
    suite = {4:20, 3:15, 2:8, 1:0, 0:0}[types]    # 0-20
    univ  = 10 if rec['in_universe'] else 0        # 0-10
    return min(100, eco + cov + suite + univ)


def pegu_grade(score):
    if score >= 80: return 'A+'
    if score >= 70: return 'A'
    if score >= 60: return 'B+'
    if score >= 50: return 'B'
    if score >= 40: return 'C+'
    return 'C'


def darvas_equiv(rec):
    if rec['has_ssf'] and rec['has_sso']: return 'OPTIONABLE_FUTURE'
    if rec['has_ssf']:                    return 'FUTURES_ONLY'
    if rec['has_sso']:                    return 'OPTIONS_ONLY'
    return 'DIVIDEND_ONLY'


def piotroski_equiv(rec):
    return {4:9, 3:7, 2:5, 1:3, 0:0}[
        sum([rec['has_ssf'], rec['has_sso'], rec['has_trf'], rec['has_div']])]


def coffee_can_equiv(rec):
    return 'PASS' if sum([rec['has_ssf'], rec['has_sso'], rec['has_trf'], rec['has_div']]) >= 3 else 'FAIL'


def cc_score_equiv(rec):
    types = sum([rec['has_ssf'], rec['has_sso'], rec['has_trf'], rec['has_div']])
    return f"{types}/4"


def main():
    print("[1/4] Fetching Eurex products...")
    products = fetch_csv(f"{BASE}/eurex_products.csv")
    print(f"      {len(products)} products")

    print("[2/4] Fetching validated universe (German stocks)...")
    univ = fetch_csv(f"{BASE}/validated_universe_flat.csv")
    # German tickers: market_code='DE', yf_symbol like 'BMW.DE'
    de_universe_symbols = {
        r['yf_symbol'].replace('.DE', '').upper()
        for r in univ if r.get('market_code') == 'DE'
    }
    print(f"      {len(de_universe_symbols)} German tickers in validated universe")

    print("[3/4] Building stock ecosystem records...")
    stocks = defaultdict(lambda: {
        'underlying': '', 'country': '', 'isin_prefixes': [],
        'has_ssf': False, 'has_sso': False, 'has_trf': False, 'has_div': False,
        'product_codes': [],
    })

    for p in products:
        if p['ProductType'] not in SINGLE_STOCK_TYPES:
            continue
        und = extract_underlying(p['Name'])
        isin_pfx = p['ProductISIN'][:2]
        rec = stocks[und]
        rec['underlying'] = und
        rec['isin_prefixes'].append((p['ProductType'], isin_pfx))
        rec['product_codes'].append(p['Product'])
        pt = p['ProductType']
        if pt == 'SINGLE STOCK FUTURES':          rec['has_ssf'] = True
        elif pt == 'SINGLE STOCK OPTIONS':        rec['has_sso'] = True
        elif pt == 'EQUITY TOTAL RETURN FUTURES': rec['has_trf'] = True
        elif pt == 'SINGLE STOCK DIVIDEND FUTURES': rec['has_div'] = True

    # Determine country: prefer SSO ISIN (actual underlying ISIN) over others
    for und, rec in stocks.items():
        sso_prefixes = [pfx for ptype, pfx in rec['isin_prefixes'] if ptype == SSO_TYPE]
        all_prefixes = [pfx for _, pfx in rec['isin_prefixes']]
        if sso_prefixes:
            # SSO ISIN is the real underlying ISIN
            country_pfx = Counter(sso_prefixes).most_common(1)[0][0]
        else:
            # No options: use any non-DE ISIN if present (might be actual underlying)
            non_de = [p for p in all_prefixes if p != 'DE']
            country_pfx = Counter(non_de).most_common(1)[0][0] if non_de else 'DE'
        rec['country'] = COUNTRY_MAP.get(country_pfx, country_pfx)
        rec['isin_pfx'] = country_pfx
        rec['n_codes'] = len(rec['product_codes'])

    # Universe matching: try ticker-style match (first meaningful word)
    for und, rec in stocks.items():
        # Try first word of underlying name as potential ticker
        words = und.upper().replace(',', '').split()
        rec['in_universe'] = any(w in de_universe_symbols for w in words if len(w) >= 2)

    print(f"      {len(stocks)} unique underlyings across all countries")
    by_country = Counter(v['country'] for v in stocks.values())
    print("\n      Country breakdown:")
    for c, n in by_country.most_common(12):
        print(f"        {c:<15}: {n}")

    # German stocks (actual German underlyings, not Eurex product ISINs)
    de_stocks = {k: v for k, v in stocks.items() if v['isin_pfx'] == 'DE'}
    print(f"\n      German underlyings: {len(de_stocks)}")
    print(f"        In validated universe: {sum(1 for v in de_stocks.values() if v['in_universe'])}")
    print(f"        With full suite (4 types): {sum(1 for v in de_stocks.values() if all([v['has_ssf'],v['has_sso'],v['has_trf'],v['has_div']]))}")
    print(f"        Grade A+/A (PEGU>=70): {sum(1 for v in de_stocks.values() if pegu_score(v)>=70)}")

    print("\n[4/4] Scoring and writing output...")

    # ── German PEGU output ─────────────────────────────────────────────────────
    de_rows = []
    for und, rec in de_stocks.items():
        score = pegu_score(rec)
        de_rows.append({
            'symbol':                und,
            'country':               rec['country'],
            'darvas':                darvas_equiv(rec),
            'piotroski':             piotroski_equiv(rec),
            'coffee_can':            coffee_can_equiv(rec),
            'cc_score':              cc_score_equiv(rec),
            'has_ssf':               int(rec['has_ssf']),
            'has_sso':               int(rec['has_sso']),
            'has_trf':               int(rec['has_trf']),
            'has_div':               int(rec['has_div']),
            'n_product_codes':       rec['n_codes'],
            'in_validated_universe': int(rec['in_universe']),
            'is_dax40':              int(is_dax40(und)),
            'pegu_score':            score,
            'pegu_grade':            pegu_grade(score),
            'market':                'DE',
        })
    de_rows.sort(key=lambda r: (-r['pegu_score'], r['symbol']))

    out = Path(__file__).parent.parent / "data" / "german_pegu_scored.csv"
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(de_rows[0].keys()))
        w.writeheader(); w.writerows(de_rows)
    print(f"  Saved: {out}  ({len(de_rows)} German stocks)")

    # ── All-Europe PEGU output ─────────────────────────────────────────────────
    eu_rows = []
    for und, rec in stocks.items():
        score = pegu_score(rec)
        eu_rows.append({
            'symbol':          und,
            'country':         rec['country'],
            'pegu_score':      score,
            'pegu_grade':      pegu_grade(score),
            'darvas':          darvas_equiv(rec),
            'piotroski':       piotroski_equiv(rec),
            'coffee_can':      coffee_can_equiv(rec),
            'cc_score':        cc_score_equiv(rec),
            'n_product_codes': rec['n_codes'],
            'in_validated_universe': int(rec['in_universe']),
            'market':          rec['isin_pfx'],
        })
    eu_rows.sort(key=lambda r: (-r['pegu_score'], r['symbol']))

    out2 = Path(__file__).parent.parent / "data" / "eurex_pegu_all_europe.csv"
    with open(out2, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(eu_rows[0].keys()))
        w.writeheader(); w.writerows(eu_rows)
    print(f"  Saved: {out2}  ({len(eu_rows)} European stocks)")

    # ── Print summary ──────────────────────────────────────────────────────────
    grade_counts = Counter(r['pegu_grade'] for r in de_rows)
    print("\n  ── German Market PEGU Grade Distribution ──────────────────")
    for g in ['A+', 'A', 'B+', 'B', 'C+', 'C']:
        bar = '█' * grade_counts.get(g, 0)
        print(f"    {g:<3}: {grade_counts.get(g,0):>4}  {bar[:40]}")

    print("\n  ── Top 30 German Stocks by PEGU Score ─────────────────────")
    print(f"  {'Stock':<38} {'Score':>5}  Grade  {'Darvas':<22} {'P':>2}  CC    DAX40")
    print("  " + "─" * 90)
    for r in de_rows[:30]:
        dax = '✓' if r['is_dax40'] else ''
        print(f"  {r['symbol']:<38} {r['pegu_score']:>5}  {r['pegu_grade']:<6} "
              f"{r['darvas']:<22} {r['piotroski']:>2}  {r['coffee_can']:<5} {dax}")

    # ── European Top 20 (cross-country) ───────────────────────────────────────
    print("\n  ── Top 20 European Stocks by PEGU Score (all countries) ───")
    print(f"  {'Stock':<38} {'Country':<14} {'Score':>5}  Grade")
    print("  " + "─" * 65)
    for r in eu_rows[:20]:
        print(f"  {r['symbol']:<38} {r['country']:<14} {r['pegu_score']:>5}  {r['pegu_grade']}")

    # ── Coffee Can breakdown ───────────────────────────────────────────────────
    de_pass = [r for r in de_rows if r['coffee_can'] == 'PASS']
    print(f"\n  ── German Coffee Can PASS stocks: {len(de_pass)} ─────────────────────")
    print(f"  {'Stock':<38} {'Score':>5}  {'CC Score':<8}  DAX40")
    print("  " + "─" * 60)
    for r in sorted(de_pass, key=lambda x: -x['pegu_score'])[:20]:
        dax = '✓ DAX40' if r['is_dax40'] else ''
        print(f"  {r['symbol']:<38} {r['pegu_score']:>5}  {r['cc_score']:<8}  {dax}")


if __name__ == '__main__':
    main()
