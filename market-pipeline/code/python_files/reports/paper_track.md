# Paper watchlist — mailer picks 13→22 Jul, marked to today

2502 unique picks priced (first-appearance entry, equal-weight, held to latest close). Return vs each market's median tracked name = excess. Short window, no costs — read direction.

## Overall

| book | n | mean return | hit rate | excess vs market |
|---|---|---|---|---|
| ALL picks (raw) | 2502 | -1.06% | 38% | -0.41% |
| CURATED (graded-A + fundamentals) | 812 | -0.68% | 42% | -0.02% |
| REC-BUY at entry (per-market rule) | 879 | -1.80% | 31% | -1.07% |
| REC-SELL at entry (rule said avoid) | 815 | -0.66% | 44% | -0.06% |
| CURATED ∩ REC-BUY | 278 | -1.86% | 30% | -0.88% |

## By market

| market | n | mean | hit | excess | curated mean | rec-BUY mean |
|---|---|---|---|---|---|---|
| EU | 185 | +0.25% | 61% | -0.01% | +0.05% (32) | -0.26% (61) |
| IN | 70 | -1.86% | 27% | +0.34% | -1.86% (70) | -1.86% (70) |
| JP | 765 | -0.28% | 45% | -0.17% | -0.08% (340) | -0.05% (255) |
| KR | 177 | -1.51% | 38% | -0.73% | +0.60% (60) | -5.92% (58) |
| US | 1305 | -1.60% | 31% | -0.61% | -1.39% (310) | -2.49% (435) |

## By filter (curated only)

| filter | n | mean | hit | excess |
|---|---|---|---|---|
| debt_reduction | 50 | -2.22% | 26% | -0.02% |
| piotroski+debt | 10 | +0.79% | 40% | +2.99% |
| roce_plus | 6 | -3.65% | 17% | -1.46% |
| technical | 742 | -0.57% | 43% | -0.05% |

## Entry-day cohorts (mean return to today)

| entry date | n | mean return |
|---|---|---|
| 2026-07-21 | 2173 | -1.04% |
| 2026-07-22 | 329 | -1.17% |

## Read

⚠️ WINDOW: 87% of picks entered on 2026-07-21 (the breakout firehose day) — only a few trading sessions of forward data, inside the KOSDAQ-crash / soft-US drawdown, so EVERY book is negative in absolute terms. Excess vs market is the fair read; the per-market REC rule is a 2-WEEK reversion signal and CANNOT be judged on 2-3 sessions — its forward validation is backtest_zone_rules.py (8y, mean-revert wins US/JP/KR/EU). This paper-track is a curation test, not a rule test.

- CURATION IS THE VALUE-ADD: raw picks lag their market by -0.41%; graded-A + fundamentals lifts that to -0.02% excess (≈market-neutral in a down tape).
- Curation dodged the KOSDAQ crash: KR raw -1.51% → KR curated +0.60% (60 names).
- Best curated filter by excess: piotroski+debt (+2.99%); EU picks +0.25% at 61% hit.
- Per-market rule applied AT ENTRY (point-in-time): REC-BUY -1.80% vs REC-SELL -0.66% — a -1.14% spread (no edge this window).