# Signal calibration — generated 2026-07-23 06:15

Ledger: 23,809 signals (2026-06-12 → 2026-07-22) · scored rows: 25,005 / 87,142 (rest pending — horizons not yet elapsed or symbol unmatched)

Prices: IN = split/bonus-ADJUSTED (full copy); JP/KR/US = yfinance-adjusted panels + confirmed residual-split overlays (overlay-first); CN/EU = yfinance-adjusted, no residuals (2026-07-23 — see gmd claims.yaml non-india-panels-already-adjusted).

## Symbol match diagnostics

| market | signals | matched | note |
|---|---|---|---|
| IN | 7384 | 7287 | 99% anchored · panel ends 2026-07-22 · 102 awaiting next bar |
| US | 14219 | 11802 | 83% anchored · panel ends 2026-07-21 · 2349 awaiting next bar |
| JP | 1570 | 1568 | 100% anchored · panel ends 2026-07-23 |
| KR | 223 | 223 | 100% anchored · panel ends 2026-07-23 |
| EU | 413 | 231 | 56% anchored · panel ends 2026-07-22 · 185 awaiting next bar |

## Outcomes by market × filter × horizon

| market | filter | h | n | hit% | median ret | median excess |
|---|---|---|---|---|---|---|
| EU | darvas BUY/long | 5.0d | 27 | 56% | +1.48% | +1.71% |
| EU | darvas BUY/long | 21.0d | 27 | 59% | +3.23% | +3.41% |
| EU | darvas SELL | 5.0d | 1 | 100% | -5.54% | -5.31% |
| EU | darvas SELL | 21.0d | 1 | 100% | -5.89% | -5.71% |
| IN | darvas BUY/long | 5.0d | 4765 | 42% | -0.82% | -0.76% |
| IN | darvas BUY/long | 21.0d | 3158 | 46% | -0.61% | -0.40% |
| IN | darvas SELL | 5.0d | 2042 | 54% | -0.21% | -0.20% |
| IN | darvas SELL | 21.0d | 1244 | 49% | +0.00% | -0.12% |
| IN | golden_cross_hist BUY/long | 5.0d | 48 | 38% | -0.69% | -0.29% |
| JP | golden_cross_hist BUY/long | 5.0d | 6 | 33% | -0.32% | +0.13% |
| KR | golden_cross_hist BUY/long | 5.0d | 1 | 0% | -10.38% | -7.80% |
| US | darvas BUY/long | 5.0d | 9066 | 58% | +0.48% | +0.11% |
| US | darvas BUY/long | 21.0d | 1751 | 66% | +2.70% | +2.10% |
| US | darvas SELL | 5.0d | 2639 | 41% | +0.75% | +0.23% |
| US | darvas SELL | 21.0d | 229 | 34% | +1.55% | +0.96% |

## Outcomes by volatility regime at signal date

Regime = tercile of the market's vol index vs its trailing ~3y window (PIT-safe, build_regimes.py). IN uses IndiaVIX; others VIX. NB: a cohort from one short window sits in one regime — read spreads only across multi-month samples.

| market | direction | h | regime | n | hit% | median ret | median excess |
|---|---|---|---|---|---|---|---|
| EU | BUY/long | 5.0d | HIGH | 27 | 56% | +1.48% | +1.71% |
| EU | BUY/long | 21.0d | HIGH | 27 | 59% | +3.23% | +3.41% |
| IN | BUY/long | 5.0d | HIGH | 773 | 56% | +0.83% | +0.05% |
| IN | BUY/long | 5.0d | MID | 4040 | 39% | -1.07% | -0.90% |
| IN | BUY/long | 21.0d | HIGH | 397 | 63% | +1.75% | +0.47% |
| IN | BUY/long | 21.0d | MID | 2761 | 43% | -0.95% | -0.55% |
| IN | SELL | 5.0d | HIGH | 281 | 42% | +1.40% | +0.62% |
| IN | SELL | 5.0d | MID | 1761 | 56% | -0.28% | -0.24% |
| IN | SELL | 21.0d | HIGH | 49 | 39% | +1.87% | +0.60% |
| IN | SELL | 21.0d | MID | 1195 | 50% | +0.00% | -0.12% |
| US | BUY/long | 5.0d | HIGH | 6950 | 58% | +0.47% | +0.01% |
| US | BUY/long | 5.0d | MID | 2116 | 57% | +0.51% | +0.51% |
| US | BUY/long | 21.0d | HIGH | 1751 | 66% | +2.70% | +2.10% |
| US | SELL | 5.0d | HIGH | 2126 | 40% | +0.74% | +0.20% |
| US | SELL | 5.0d | MID | 513 | 44% | +0.75% | +0.75% |
| US | SELL | 21.0d | HIGH | 229 | 34% | +1.55% | +0.96% |
