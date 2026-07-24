# Strategy Performance Report — Template & Live Instance

**Reporting template modeled on GIPS 2020 + SEBI PMS disclosure conventions,
distilled from PPFAS / Marcellus / Motilal Oswal factsheets, Third Point /
Greenlight investor-letter structure, and Virtu Financial's market-maker ROI
framework.** Section skeleton is reusable; the filled numbers are this
platform's live strategies as of 2026-07-24.

> Not investment advice or a solicitation. Realized backtest / research
> statistics on internally-recorded signals; past performance does not predict
> future results. Figures are pre-tax; the validated leg is net-of-modeled-cost,
> others are gross where noted.

---

## 1. HEADER

| Field | Strategy A — CA Intimation Drift | Strategy B — Multi-Market Darvas Scan |
|---|---|---|
| Objective | Capture the pre-ex-date drift after a bonus/split board-meeting intimation | Momentum breakout watchlist across 6 markets |
| Base currency | INR | Local / USD-normalized |
| Inception (data) | 2016 (10y CA history) | 2016 (10y panels) |
| Benchmark | NIFTY Midcap TRI (daily market median used in-study) | Market-median return per market |
| Universe | NSE-listed names with a board-meeting intimation | IN/US/EU/JP/KR/CN warehouse (≈24k symbols) |
| Status | **VALIDATED** (split leg, FDR q=0.05) | Research funnel (uncosted) |
| Capacity | ~Rs 10Cr/yr through split leg at Rs 2Cr/position | n/a (watchlist generator) |

---

## 2. STRATEGY & SCREENING CRITERIA  *(Element 1)*

**Strategy A — filters (fully mechanical, point-in-time):**
- **Trigger**: NSE board-meeting intimation whose purpose text contains
  bonus / split / sub-division (source: `corporate-board-meetings` API).
- **Entry**: intimation broadcast + 2 trading days (after-15:30 → next day).
- **Exit**: ex-date − 1 trading day.
- **Universe gate**: position ≤ 10% of the name's trailing-120d median daily
  turnover (executability cap — non-negotiable; fills above it are fiction).
- **Sizing**: equal-weight per event; concurrent positions = book ÷ position.
- **No qualitative overlay** — the edge is the calendar mechanic itself.

**Strategy B — filters:**
- Darvas box breakout (current bar excluded from box) + above-EMA50 + RSI-healthy
  + near-52w-high; BUY ≥ 5 / WATCH ≥ 3 on the 0–7 Darvas/Buffett scale.
- Universe: warehouse panels; India adjusted, others yf-adjusted + residual
  split overlays.

---

## 3. PERFORMANCE SUMMARY  *(Element 5)*

**Strategy A — CA Intimation Drift (abnormal vs market median, adjusted prices):**

| Leg | n | Gross drift / event | Net-of-cost / event | Hit% | Median hold (td) | Annualized* |
|---|---|---|---|---|---|---|
| **Split** | 258 | +16.5% | **+10.3% to +13.7%** | 83% | 50 | +116% |
| Bonus | 295 | +10.4% | +8.0% | 75% | 35 | +104% |

\*Annualized = single-cycle return scaled by 252/holding-days; illustrative —
capacity-bound, not compoundable at that rate. Net range spans Rs 1L→Rs 2Cr
position sizes (cost rises with size).

**Strategy B — Darvas BUY, marked to +5d / +21d forward:**

| Market | Horizon | n | Mean | Hit% | Median excess | Sharpe |
|---|---|---|---|---|---|---|
| US | +5d | 9,066 | +1.33% | 58% | +0.11% | 1.08 |
| US | +21d | 1,751 | +2.90% | 66% | +2.10% | 0.62 |
| IN | +21d | 3,158 | −0.33% | 46% | −0.40% | −0.13 |

All-market BUY +21d: +0.83% gross, +10.5% annualized, Sharpe 0.24 (uncosted).

---

## 4. RISK & CONSISTENCY  *(Element 5)*

| Metric | Strategy A (split) | Strategy B (US +21d) |
|---|---|---|
| Hit rate / batting avg | 83% | 66% |
| Sharpe (per-cycle annualized) | ~2.0 (t=5.8 on quarterly excess) | 0.62 |
| Worst single event | (in parquet; see event tails) | — |
| Sample / regime | single 10y window, no subperiod split yet | 2016–26, regime-labelled |
| Capacity | ~Rs 10Cr/yr (split leg, Rs 2Cr/pos, 10%-ADV) | n/a |
| **Statistical status** | **survives BH-FDR q=0.05 across 18-hypothesis family** | not FDR-tested (funnel) |

Regime conditioning available: outcomes split by trailing-VIX/IndiaVIX terciles
(`build_regimes.py`) — IN Darvas BUY 21d hits 63% in HIGH-vol vs 43% MID.

---

## 5. PORTFOLIO & ACTIONS  *(Element 2)*

**Live watchlist — Strategy A open positions (intimation→ex window, 2026-07-24):**

| Symbol | Intimation | Kind | Status | ADV Rs Cr | Action |
|---|---|---|---|---|---|
| GOODLUCK | Jul 07 | bonus | in window | 18.6 | HOLD (mid-window) |
| CORDELIA | Jul 08 | split | in window | 124.5 | HOLD (liquid, weaker drift) |
| AASTHA | Jul 20 | bonus | fresh | 2.7 | BUY-eligible (day +3) |
| HARDWYN | May 29 | bonus | in window | 11.1 | HOLD |
| TEMBO | Jun 11 | split | in window | 6.1 | HOLD |
| NARMADA | May 25 | split | late-window | 1.8 | REDUCE (near ex) |
| TCC | Jul 16 | split | in window | 0.3 | SKIP (fails ADV cap) |

*Buy/Hold/Sell here = position lifecycle vs the ex-date, not a valuation rating.
Cross-check each vs screener.in before acting (standing rule).*

**Attribution — top contributors (backtest, split leg):** the tail of high-drift
small-caps drives the mean; median (not mean) is the honest central estimate.

---

## 6. P&L & ATTRIBUTION  *(Element 3)*

- **Gross vs net shown side-by-side** (Section 3): split gross +16.5% → net
  +10.3–13.7% after Corwin-Schultz spread + Amihud impact + 0.2% commissions.
- **Realized basis**: every figure is a realized forward return on adjusted
  prices; no unrealized marks (event windows are closed).
- **Attribution by leg**: split >> bonus; by regime: HIGH-vol favours IN momentum.
- **Negative results reported** (the discipline): announcement-sorted PEAD
  (Q5−Q1 +0.86%, fails FDR), post-ex drift (~0%), all 12 factor-combo cells
  (0/12 survive FDR). Reporting these is mandatory, not optional.

---

## 7. FEES & COSTS  *(Element 4)*

| Cost component | Treatment in this report |
|---|---|
| Transaction cost | Corwin-Schultz spread (per-event, PIT) + Amihud impact × size |
| Commissions/STT/stamp | 0.2% round trip (India retail) — charged |
| Slippage | participation-capped at 10% ADV (implicit slippage guard) |
| **Cost of capital / hurdle** | benchmark = daily market-median return (excess is over this hurdle) |
| Management/performance fee | n/a (proprietary research) — **template placeholder**: e.g. 2.5% fixed + 20% over 8% hurdle, high-water mark |
| Turnover | Strategy A ~1 round trip/event, 35–50 td holds |

Median all-in cost, Strategy A split: **~1.0% per round trip** — small vs the
+10–16% gross, which is why the edge is capacity-bound not cost-bound.

---

## 8. DISCLOSURES  *(regulatory anchors)*

- **GIPS-style**: gross AND net shown; benchmark = TRI/market-median stated;
  no sub-1yr annualization presented as compounded; std-dev/Sharpe on the
  validated leg. (Not a GIPS-compliance *claim* — a proprietary research report.)
- **SEBI-PMS-style** (if productized): TWRR headline + client XIRR, one specified
  benchmark per approach, net-of-all-fees, cash included, auditor certification,
  APMI-comparable format.
- **Methodology**: adjusted prices (`price_adjuster*.py`), PIT event timing
  (broadcast timestamp), matched-benchmark + BH-FDR validation
  (`validate_intimation_drift.py`), cost model (`cost_intimation_drift.py`).
  Claims ledger: `global-market-data/claims.yaml`.
- **Caveat**: single 10y sample; split leg validated, bonus leg provisional;
  live slippage beyond the model unquantified; past performance ≠ future results.

---

### How to regenerate
`recommendation_roi.py` (P&L), `pit_event_studies.py` (drift), `cost_intimation_drift.py`
(costs), `validate_intimation_drift.py` (FDR), `build_regimes.py` (regime) →
all write into `reports/`. This template stitches their outputs into the
professional 8-section layout above.
