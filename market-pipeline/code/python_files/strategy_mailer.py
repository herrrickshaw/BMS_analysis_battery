#!/usr/bin/env python3
"""
strategy_mailer.py — turn the session's validated learnings into a watchlist + email.

Adds the validated cheap+high-ROE longs (per-market, tagged `value-hold` so the
trend-based eviction leaves them alone) to watchlist.csv, then composes a strategy
digest — the suitability matrix's deployment rules + the picks with valuation
rationale — and sends it to MAIL_TO (self). Research/paper-track, not advice.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import send_mailer as SM
from obs import get_logger, DecisionLog

HERE = Path(__file__).resolve().parent
LOG = get_logger("strategy_mailer")
ASOF = "2026-07-24"

# validated cheap+high-ROE longs (reports/valuation_clusters.csv, ACCUMULATE clusters)
PICKS = {
 "IN": [("VEDL","Vedanta",5.9,43),("IOC","Indian Oil",4.7,19),("BPCL","BPCL",5.2,26),
        ("HINDPETRO","HPCL",4.5,28),("COALINDIA","Coal India",8.5,26),
        ("NATIONALUM","Natl Aluminium",12.1,30),("SIGNATURE","Signatureglobal",9.8,59),
        ("ACCELYA","Accelya",13.3,46)],
 "US": [("AOS","A.O. Smith ⭐",8.2,29),("LULU","Lululemon",7.8,32),("ANF","Abercrombie",8.0,36),
        ("ALC","Alcon",9.2,30),("ACN","Accenture",11.5,25),("IBEX","IBEX",11.7,27)],
 "KR": [("015760.KS","KEPCO",2.5,18),("002380.KS","KCC",2.4,20),("071320.KS","KDHC",2.2,15),
        ("020710.KQ","Sigongtech",2.3,16),("007370.KQ","Jinyang Pharm",2.4,14)],
}
DEPLOY = [
 ("🇮🇳 India","momentum/trend","breakout + sector-relative value (long-only)","❌ never short — bull runs shorts over"),
 ("🇺🇸 US","mixed","golden-cross / cheap+quality, light","marginal"),
 ("🇰🇷 Korea","mean-reversion","cheap∩hi-ROE (the Korea discount)","✅ short hollow-overpriced (validated t4.2)"),
]


def update_watchlist():
    wl = pd.read_csv(HERE / "watchlist.csv")
    have = set(zip(wl.symbol.astype(str).str.upper(), wl.market.astype(str).str.upper()))
    new = []
    for mkt, rows in PICKS.items():
        for sym, name, pe, roe in rows:
            key = (sym.upper(), mkt)
            if key in have:
                continue
            new.append({"symbol": sym, "market": mkt, "status": "value-hold",
                        "note": f"value-cluster PE{pe} ROE{roe}% (validated reversion) {ASOF}",
                        "entry_date": ASOF, "entry_price": ""})
    if new:
        pd.concat([wl, pd.DataFrame(new)], ignore_index=True).to_csv(HERE / "watchlist.csv", index=False)
    LOG.info(f"watchlist: +{len(new)} value-hold picks (exempt from trend eviction)")
    return len(new)


def html():
    C = {"bg": "#0B2F4A", "accent": "#0c6b58", "muted": "#8aa0ae"}
    def pick_rows(mkt):
        out = ""
        for sym, name, pe, roe in PICKS[mkt]:
            out += (f'<tr><td style="padding:5px 8px"><b>{sym}</b> '
                    f'<span style="color:{C["muted"]};font-size:12px">{name}</span></td>'
                    f'<td style="text-align:right;padding:5px 8px">PE {pe}</td>'
                    f'<td style="text-align:right;padding:5px 8px;color:{C["accent"]}">ROE {roe}%</td></tr>')
        return out
    dep = "".join(f'<tr><td style="padding:5px 8px">{m}</td><td style="padding:5px 8px">{c}</td>'
                  f'<td style="padding:5px 8px">{l}</td><td style="padding:5px 8px;font-size:12px">{s}</td></tr>'
                  for m, c, l, s in DEPLOY)
    blocks = ""
    for mkt, title in [("IN","🇮🇳 India — cheap + high-ROE (long-only)"),
                       ("US","🇺🇸 US — value + quality"),
                       ("KR","🇰🇷 Korea — the discount (reversion strongest)")]:
        blocks += (f'<h3 style="color:{C["bg"]};margin:18px 0 6px">{title}</h3>'
                   f'<table style="border-collapse:collapse;width:100%;font-size:14px;'
                   f'border:1px solid #dfe7ec">{pick_rows(mkt)}</table>')
    return f'''<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a2b34">
<h2 style="color:{C["bg"]}">📊 Strategy digest — validated picks & suitability</h2>
<p style="font-size:14px;color:{C["muted"]}">Cheap + high-ROE longs where valuation reversion is
statistically validated (IN/US/KR). Peers are data-driven economic clusters; reversion corrects
over/under-pricing (+5–6%/6M, backtested). Paper-track, <b>not investment advice</b>.</p>
<h3 style="color:{C["bg"]};margin:18px 0 6px">Deployment rules (market character)</h3>
<table style="border-collapse:collapse;width:100%;font-size:13px;border:1px solid #dfe7ec">
<tr style="background:#eef3f6"><td style="padding:5px 8px"><b>market</b></td><td style="padding:5px 8px"><b>character</b></td>
<td style="padding:5px 8px"><b>long</b></td><td style="padding:5px 8px"><b>short</b></td></tr>{dep}</table>
{blocks}
<p style="font-size:12px;color:{C["muted"]};margin-top:18px">Added to watchlist as <code>value-hold</code>
(exempt from trend-eviction so the paper-track can actually measure the reversion). ⭐ = triple-convergence
(value ∩ quality ∩ momentum). Full suitability matrix: reports/strategy_matrix.md. yfinance/screener
fundamentals, latest FY. Educational research — consult a SEBI-registered advisor.</p></div>'''


def main() -> int:
    n = update_watchlist()
    DecisionLog().record("strategy_mailer", picks_added=n, markets=list(PICKS),
                         n_picks=sum(len(v) for v in PICKS.values()))
    subject = f"📊 Strategy Digest — {sum(len(v) for v in PICKS.values())} validated value picks (IN/US/KR) · {ASOF}"
    text = "Validated cheap+high-ROE longs across IN/US/KR + deployment matrix. Paper-track, not advice."
    SM.send(subject, text, html())
    LOG.info(f"sent strategy digest ({n} new watchlist picks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
