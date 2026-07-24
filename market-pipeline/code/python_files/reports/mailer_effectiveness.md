# Mailer effectiveness — signals 13–22 Jul 2026 (+ backfilled history)

## 1. Recent window (ledger signals → today, 4,667 priced rows)
CAVEAT: 1.5 weeks, unadjusted for the KOSDAQ crash (Jul 16/20) and soft US tape —
raw returns, short horizon, read direction not magnitude.

| filter | n | raw since-signal | hit rate |
|---|---|---|---|
| piotroski+debt | 24 | +0.13% | 38% |
| piotroski | 28 | −0.38% | 36% |
| technical (breakout) | 4,463 | −0.49% | 45% |
| debt_reduction | 126 | −1.03% | 27% |
| roce_plus | 18 | −1.70% | 22% |

| market | n | raw | hit |
|---|---|---|---|
| EU | 370 | +0.25% | 61% |
| JP | 1,528 | −0.28% | 45% |
| US | 2,346 | −0.67% | 43% |
| IN | 204 | −0.91% | 29% |
| KR | 219 | −1.17% | 39% |

## 2. Matured outcomes (score_signals backfill, market-adjusted EXCESS)
| filter | horizon | n | excess vs mkt | hit |
|---|---|---|---|---|
| darvas | 5d | 18,540 | +0.41% | 49% |
| darvas | 21d | 6,410 | +0.68% | 51% |
| golden_cross_hist | 5d | 55 | +0.46% | 45% |

- darvas excess by market: US +0.92%/5d (hit 52%) vs INDIA −0.46%/5d (hit 43%)
  — breakout momentum works in the US, NOT in India (consistent with the
  global-strategy finding).
- Regime: HIGH-vol signals +0.78%/5d excess vs MID −0.03% — breakouts earn
  their keep only when vol is elevated.

## 3. Hygiene rules validated
Purged names (>15 sessions in sell zone, n=80 priced): mean −4.58% over the
last 5 sessions, 63/80 still falling — the purge removes genuine decliners,
not winners being shaken out.

## Verdict & actions
1. The mailer's TECHNICAL firehose (4.5k signals/10d) is noise at the mean;
   the top-5-per-market watchlist cap is what makes it usable. Keep the cap.
2. INDIA: momentum/breakout signals are the weakest (−0.91%, 29% hit) while
   sector-relative VALUE backtests strongly (+5.3%/6M) — weight India toward
   value_rerating, US toward breakout/darvas.
3. Consider regime-gating technical promotions (HIGH-vol only) — the MID
   regime edge is zero.
4. Eviction/purge machinery is doing its job; no change needed.
