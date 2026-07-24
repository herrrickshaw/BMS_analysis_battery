# Recommendation ROI & earnings — 2026-07-24

CFO-level P&L on the platform's two recommendation books, marked to realized forward returns on split/bonus-adjusted prices. Returns are per-signal; annualized ROI scales the mean by the holding period. NOT personalized advice — realized backtest statistics on recorded recommendations.

## Book A — daily scan signals (Darvas / golden-cross)

18,595 scored signals · 23,809 still pending (horizon not elapsed).

| market | dir | horizon | n | mean ret | hit% | ann ROI | median excess | Sharpe |
|---|---|---|---|---|---|---|---|---|
| IN | BUY | 5d | 4,813 | -0.59% | 42% | -25.9% | -0.75% | -0.40 |
| IN | BUY | 21d | 3,158 | -0.33% | 46% | -3.8% | -0.40% | -0.13 |
| US | BUY | 5d | 9,066 | +1.33% | 58% | +94.7% | +0.11% | 1.08 |
| US | BUY | 21d | 1,751 | +2.90% | 66% | +41.0% | +2.10% | 0.62 |

**All-market BUY, +21d:** 4,936 signals, +0.83% mean (53% hit), annualized ROI +10.5%, Sharpe 0.24. This is a gross, cost-free, equal-weight read — the scan is a watchlist generator, not a costed strategy.

## Book B — CA intimation drift (validated, FDR-surviving)

Enter intimation+2 trading days, exit ex−1. Abnormal return vs market median on adjusted prices. Split leg is the FDR survivor (see claims.yaml `india-ca-intimation-drift`).

| kind | n | mean drift | hit% | median hold (td) | ann ROI |
|---|---|---|---|---|---|
| bonus | 295 | +10.37% | 75% | 35 | +103.5% |
| split | 258 | +16.48% | 83% | 50 | +115.7% |

### Cost-adjusted economics (split leg, per COST_INTIMATION_DRIFT.md, 10%-ADV cap over ~2.5yr of events)

| position/event | executable events (2.5yr) | net/event | earnings/event | events/yr |
|---|---|---|---|---|
| Rs 1L | 223 | +13.7% | Rs 0.14L | ~89 |
| Rs 10L | 157 | +13.1% | Rs 1.31L | ~63 |
| Rs 50L | 101 | +10.4% | Rs 5.20L | ~40 |
| Rs 2Cr | 52 | +10.3% | Rs 20.60L | ~21 |

Read — per position, not per book: each split event returns net +10-14% over ~50 trading days. ROI is book-size-flat (cost is ~1%); what shrinks with size is the COUNT of executable events (223 → 52 as the 10%-ADV cap bites). Portfolio earnings = position × net × concurrent slots your book can fund — at Rs 1L you can take nearly every event (~90/yr); at Rs 2Cr only the ~20 liquid ones/yr. Absolute rupees therefore depend on total book size, not position size; the durable statement is the book-size-flat +10-14%/event net ROI. Platform's only cost-and-FDR-validated edge.

## Overall

- **Validated ROI edge:** CA intimation drift (split), net-of-cost +10-14%/event, FDR-surviving.
- **Watchlist ROI (indicative):** all-market Darvas BUY +21d +0.83% gross (+10.5% annualized) — uncosted, use as a funnel not a P&L.
- **Dead on arrival:** announcement-sorted PEAD, post-ex drift, all 12 factor-combo cells (0 survive FDR).

The honest CFO summary: one recommendation stream clears the bar for real capital; the rest are research funnel or negative results — which is itself the deliverable the FDR discipline was built to produce.
