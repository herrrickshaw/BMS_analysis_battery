# Liquidity, Not Size, Conditions the Piotroski F-Score Premium

### Evidence from US equities, 2016–2026, with point-in-time filing dates

**Research note · 15 July 2026 · Educational and research use only. Not investment advice.**

---

> ## 🔴 STATUS: NUMBERS BELOW ARE BEING REGENERATED
>
> Adversarial validation (five independent agents, each instructed to *refute* rather than
> confirm) found **eight defects** after this note was drafted. Three are fixed, one is
> documented-and-unfixed, and a re-collection is running. **Every figure here should be
> read as provisional until that lands.**
>
> | | |
> |---|---|
> | **Fixed — invalidates the tables below** | US `revenue` stored the ASC-606 *contract-revenue subset*, not total revenue. ADM FY2023 held **$25.69B against a 10-K total of ~$93.9B — wrong by 3.7×**. `cost_of_revenue > revenue` (impossible) fired on 262/5,418 rows. Revenue feeds Piotroski tests 8 and 9, so this **flips booleans**, and it skews to multi-segment filers — i.e. large caps, i.e. the cell carrying the headline. |
> | **Documented, NOT fixed** | `EBIT = PBT + interest` is **wrong for lenders** — for a bank/NBFC interest is cost of goods sold. EBIT inflates ~4×, capital employed ~9×, and **the errors partially cancel into the 5–25% plausible band**, so no range check can fire. It survived validation because the checks used (RELIANCE 8.9%, TCS 56.8%) are both non-financials. **ROCE for Indian lenders is wrong and there is no guard.** |
> | **Fixed** | Per-market liquidity floors were **fabricated** — US $475k reproduced under no universe definition (measured: $300k with junk, $896k without). The "India 47th percentile" anchor existed only because 1,079 of 3,476 panel names are delisted. Deleted, not recomputed. |
> | **Fixed** | `(x or 0)` silently voids NaN — `float(str(nan))` succeeds so the `None` fallback never fires, and **NaN is truthy**. Voided 15% of gate-passing rows. |
>
> **Coverage rose 13% → 43%** of available tickers once the broken price panel and an
> inconsistent field requirement were fixed. Sample sizes throughout are therefore
> understated.

---

## Abstract

We test whether the Piotroski (2000) F-score premium is conditioned by firm size or by
stock liquidity — two attributes that are heavily entangled and are routinely conflated.
Using SEC EDGAR fundamentals gated on **actual filing dates** and a survivorship-complete
price panel, we find the F-score premium tracks **illiquidity, not size**. Double-sorting
liquidity within size, illiquid names out-earn liquid names in *both* size buckets, and
the largest premium (+33.7pp median) appears in **large-capitalisation but illiquid**
firms — not small caps. The only negative cell is large-and-liquid (−1.7pp).

We separately confirm Fang, Noe & Tice (2009): return on capital employed rises
monotonically with liquidity (11.0% → 21.6% ex-cash). Better companies are more liquid;
better *investments* are not. A Corwin–Schultz + Amihud cost model bounds the strategy's
capacity at roughly **$300–500k**, above which it is unprofitable — consistent with the
F-score literature's finding that the premium is unreachable at institutional scale.

We report six derived metrics that failed validation and were discarded, and note that
mean and median disagreed on **every** headline result, with the median correct each time.

---

## 1. Introduction

Piotroski (2000) locates the F-score premium in "small, illiquid, low-analyst-coverage
value stocks." Three attributes, routinely compressed into one — usually *size*, because
size is the conventional risk factor and the easiest to measure.

This note asks which attribute is doing the work. The question is not academic: size and
liquidity imply different portfolios, different capacity, and different mechanisms.

Two literatures make opposing predictions that must be held apart:

- **Fang, Noe & Tice (2009)** — liquidity *causally improves firm performance* (Tobin's Q,
  operating ROA), via a feedback channel where informed trading makes prices more
  informative. Predicts **liquid firms are better firms**.
- **Amihud (2002)** — illiquid stocks earn **higher returns** as compensation for illiquidity,
  with the effect strongest among small firms. Predicts **illiquid stocks are better
  investments**.

Both can hold simultaneously. Better companies need not be better investments.

## 2. Data

| | |
|---|---|
| **Fundamentals** | SEC EDGAR, 4,597 tickers, 111,949 filings |
| **Prices** | 10.5y point-in-time panel, 9.0M rows |
| **Usable panel** | 3,294 stock-years · 597 symbols · 9 annual rebalances (2017–2025) |
| **Daily-scan panel** | 12,773 breakout signals · 636 symbols · 10 years |

**Point-in-time integrity.** Entry is gated on EDGAR's `filed` field — the actual filing
date, carrying 1,449 distinct fiscal-end-to-filing lags including a 2009 fiscal year filed
in 2012. This is a true as-of date, not a reporting-lag assumption. Filing lags are
constrained to 0–400 days: negatives are impossible, and longer gaps are restatements
whose filing date no longer marks when the market learned the numbers.

**Survivorship.** The price panel retains delisted names (964 of 3,476 in the India
comparison set stop trading and are kept). Delisting exits at the last traded close rather
than being dropped — dropping is how backtests invent alpha, since a stock that dies is
usually a stock that fell.

**Corporate actions.** The panel stores raw close, not adjusted close. Unfiltered, splits
manufactured a spurious +12.20% mean forward return with 248% standard deviation
(`GOLDBEES` 3359.60 → 33.55 is a 1:100 unit split, not a −99% crash). Filtering single-day
moves outside [−50%, +100%] collapses that standard deviation to **29%**.

## 3. Method

The F-score is computed unmodified (9 tests). A separate 3-point ROCE block — level
(ex-cash), 5-year stability, trend — is reported alongside, never merged, so the F-score
stays comparable to published results and the block's marginal contribution stays
measurable. Their rank correlation is **+0.236** (n=288) and **+0.239** (n=150,
independent): they are complements, not substitutes.

Returns are winsorised 1/99 per rebalance. **Median is the headline throughout.**

## 4. Results

### 4.1 The premium tracks illiquidity, not size

Turnover and market capitalisation correlate at **+0.797**. Ranking on turnover alone —
as we initially did — cannot distinguish them. Double-sorting liquidity *within* size,
with capitalisation measured point-in-time (last close × shares as filed):

| Size | Liquidity | n | F≥70 | F<40 | **Premium** | @818 | @1,673 |
|---|---|---|---|---|---|---|---|
| Small | **Illiquid** | 2,703 | +3.4% | −10.0% | **+13.4pp** | +13.8 | +12.2 |
| Small | Liquid | 2,703 | +4.6% | −2.9% | +7.5pp | +7.7 | **+13.9** |
| **Large** | **Illiquid** | 2,703 | +6.8% | **−24.6%** | **+31.4pp** | +33.7 | +27.8 |
| Large | Liquid | 2,702 | +8.2% | +0.9% | **+7.4pp** | **−1.7** | +3.6 |

Illiquid beats liquid **within both size buckets**. The largest premium is in **large,
illiquid** firms — 4× the next cell.

**The last two columns are the honest part of this table.** The same four cells were
computed at three sample sizes as data defects were fixed, and they did not all hold:

- **Small+Liquid reversed and reverted.** At n=1,673 it read +13.9 and appeared to *beat*
  illiquid — contradicting the paper's thesis. At n=2,703 it settles back to +7.5. The
  middle run was the outlier; the thesis was retracted on it and then restored.
- **Large+Liquid moved monotonically** −1.7 → +3.6 → **+7.4** as data was added. An earlier
  draft called it "the only negative cell." **That claim is withdrawn: it is positive.**
  The premium is smallest there, not absent.
- **Large+Illiquid and Small+Illiquid are stable** across all three (+31 to +34, +12 to +14).

A claim that survives a 3.3× increase in sample is worth more than one that doesn't. Two
of these four did; two did not. The thesis rests on the two that did.

**Mechanism.** In the strongest cell, illiquid large-caps with weak fundamentals *crash*
(F<40 median −25.6%): value traps, low float, distressed names institutions cannot exit.
The F-score identifies them. The premium is largely downside avoidance, not upside capture.

### 4.2 Liquidity predicts firm quality — the Fang–Noe–Tice channel

Return on capital employed, India, 360-firm stratified sample:

| Tier | ROCE | **Ex-cash** | Cash as % of capital employed | 5y CV | High **and** stable |
|---|---|---|---|---|---|
| Large | 17.9% | **21.6%** | 20.0% | 0.22 | 39% |
| Mid | 14.9% | **17.7%** | 17.6% | 0.21 | 40% |
| Small | 9.6% | **11.0%** | 9.5% | 0.34 | 13% |

Monotonic, and the whole distribution shifts. **Cash correction matters and is uneven**:
large firms hold 20.0% of capital employed in cash versus 9.5% for small, so the raw
figure penalises the strongest balance sheets. Correcting widens the gap from 8.3pp to
10.6pp.

The stability cliff sits between **mid and small**, not large and mid — mid-caps are as
consistent as large-caps (CV 0.21 vs 0.22).

**This confirms Fang–Noe–Tice while §4.1 confirms Amihud.** Liquid firms are better
businesses; illiquid stocks are better investments. Both are true.

### 4.3 Capacity

Costs are estimated from data, not assumed: **Corwin–Schultz (2012)** recovers the
bid-ask spread from daily high/low bars (no quote data required); **Amihud ILLIQ** supplies
price impact scaled by position size.

The illiquid tier's median stock trades **$0.16M/day**, and its median spread is **1.09%**.
A 10-position portfolio at each capital level, gross premium +13.3% (best vector):

| Capital | Per position | Cost/yr | % of ADV | **Net premium** | Verdict |
|---|---|---|---|---|---|
| $1,000 | $100 | 1.10% | 0.06% | **+12.2%** | profitable |
| $10,000 | $1,000 | 1.18% | 0.61% | **+12.1%** | profitable |
| $50,000 | $5,000 | 1.54% | 3.04% | **+11.8%** | profitable |
| $100,000 | $10,000 | 1.99% | 6.08% | **+11.3%** | profitable |
| $250,000 | $25,000 | 3.34% | 15.19% | **+10.0%** | profitable — near ceiling |
| $500,000 | $50,000 | 5.60% | **30.4%** | +7.7% | not executable |
| $1,000,000 | $100,000 | 10.10% | **60.8%** | +3.2% | not executable |
| $2,000,000 | $200,000 | 19.12% | **122%** | −5.8% | not executable |
| $10,000,000 | $1,000,000 | 91.23% | **608%** | −77.9% | not executable |

**Two distinct ceilings, and the binding one is not cost.** Below ~$250k the premium is
stable at +10% to +12%, because cost is dominated by the 1.09% spread, which does not scale
with size. Above ~$250k the position exceeds ~15–20% of average daily volume — the practical
limit for building a position in one day near the quoted price. Beyond that the model is not
pricing a trade; it is reporting that the trade does not exist.

**The capacity ceiling is therefore ≈ $250,000**, set by execution, not by fees. Impact is
charged linearly where real impact convexifies, so this is an upper bound.

This is a **retail-scale premium, unreachable at institutional scale**. A fund deploying $10M
would need 608% of the median name's daily volume. That is a plausible reason the premium
persists twenty-five years after publication: it cannot be arbitraged by anyone large enough
to matter.

### 4.4 The F-score does not improve breakouts

Prior internal work reported that the F-score "fails as a stock-picker, works as a breakout
overlay" (+9.9pp median). Scanning **daily** rather than annually (12,773 signals vs 117):

| Tier | Baseline | Darvas alone | Darvas × F≥7 | Darvas × F≤3 |
|---|---|---|---|---|
| Illiquid | −5.1% | **+2.0%** | +2.7% | **+3.9%** |
| Mid | −1.6% | **+7.6%** | +6.7% | +1.0% |
| Liquid | +4.2% | **+3.9%** | **−0.1%** | +0.8% |

Darvas breakouts carry signal in every tier. **The F-score overlay does not add** — negligible
in illiquid, worse in mid, destroys the edge in liquid. The overlay result did not reproduce.

## 5. What failed

Six derived metrics looked populated and plausible and were wrong. **Every one was caught by
an independent check; none by reasoning.**

| Metric | Failure | Caught by |
|---|---|---|
| ROCE via ratio inversion | 95–137% (real: 5–25%) | plausibility range |
| Quarterly operating profit | would splice quarterly into annual, ~4× wrong | reading source structure |
| Illiquidity premium | +12.20% mean, 248% sd — unadjusted splits | `GOLDBEES` 3359→33.55 |
| Current-ratio proxy | 62.1% sign agreement vs 57.6% coin-flip baseline | independent ground truth |
| Gross margin | 98% for a services firm (true ~42%) | raw materials = 0.1% of sales |
| Darvas gradient | reversed under proper power | 117 → 12,773 signals |
| **US price panel** | **interrupted alphabetical collection** — CME, Cummins and all of D–L absent; the 597-ticker sample held only A,B,C,M,N,P,Q,R,S,T | comparing symbol counts against EDGAR |
| **US revenue tag** | ASC-606 subset stored as total — ADM 3.7× wrong | `cost_of_revenue > revenue` is impossible |
| **Lender EBIT** | interest added back for banks/NBFCs; errors cancel **into the plausible band** | ROE cross-check on financials |
| **Per-market floors** | fabricated — reproduce under no universe definition | recomputing them |
| **`(x or 0)`** | NaN is truthy; `float(str(nan))` succeeds | executing it |

**Three of these were corrections to this analysis's own conclusions, and three more were
fixes I proposed that the data refuted *before they shipped*:**

- an `interest/revenue ≥ 25%` lender gate — **caught Adani Power (a power utility), missed
  360ONE and 5PAISA (both NBFCs)**. Interest/revenue measures leverage, not lending.
- *"bonds pass the value gate on face value"* — **0 of 446 clear ₹1 crore; median bond
  turnover is ₹0.9 lakh/day.** Reasoned from a precedent instead of measuring.
- the per-market floors above, asserted as "the 47th percentile" without recomputation.

Each was a plausible mechanism asserted without a check. **The pattern, not the individual
bugs, is the finding**: a mechanism that sounds right is not evidence, and the six original
failures share that shape exactly.

**Mean and median disagreed on every headline result** — the illiquidity premium, the
"inversion", low-F outperformance (117% mean vs 15.1% median). The median was correct each
time. A published claim that "US Piotroski is inverted" proves substantially a
**winsorisation artefact**: unwinsorised the mean inversion is 10.5pp; winsorised, 1.2pp.

## 6. Limitations

1. **Power.** 8–10 rebalances. Stocks co-move within a rebalance, so effective n approaches
   the rebalance count, not the row count. No standard errors are reported because none
   would be credible.
2. **No factor controls.** Amihud and Fang–Noe–Tice control for beta, size and book-to-market.
   We control for size only (§4.1), and imperfectly — `corr(turnover, mcap) = +0.797` means
   the cells are separable but not orthogonal.
3. **Range restriction.** The sample sits at the 77th percentile of US liquidity. "Illiquid"
   here is relative to a large-cap universe; genuinely small names are untested.
4. **Survivorship in fundamentals.** EDGAR retains filings from firms that later delisted, but
   firms that never filed are absent. Results are an upper bound.
5. **Regime, not skill.** The year-by-year series is dominated by regime: −28.1% in 2020,
   +14.4%/+7.1% in 2021–22, negative through 2024–25. Ten years cannot separate the two.

## 7. Conclusion

The Piotroski premium is conditioned by **liquidity, not size** — the attribute the original
paper named alongside size and which subsequent practice tends to drop. It is strongest where
illiquidity coincides with weak fundamentals, and it operates mainly by avoiding disasters
(F<40 median −25.6%) rather than by selecting winners. It disappears exactly where theory
says it should: in large, liquid, efficiently priced names.

Its capacity is roughly **$300–500k**, which is likely why it persists. The premium is real,
small, retail-scale, and measured on a sample too short to trade with confidence.

The most durable finding is methodological: **derived metrics must be validated against an
independent source before use.** Six failed here. All six would have produced publication-shaped
tables.

---

### References

- Amihud, Y. (2002). Illiquidity and stock returns: cross-section and time-series effects. *Journal of Financial Markets* 5(1), 31–56.
- Corwin, S. & Schultz, P. (2012). A simple way to estimate bid-ask spreads from daily high and low prices. *Journal of Finance* 67(2).
- Fang, V., Noe, T. & Tice, S. (2009). Stock market liquidity and firm value. *Journal of Financial Economics* 94(1).
- Piotroski, J. (2000). Value investing: the use of historical financial statement information to separate winners from losers. *Journal of Accounting Research* 38.
- Walkshäusl, C. et al. The Piotroski F-Score: a fundamental value strategy revisited from an investor's perspective. EconStor.

*Reproduction: `sweep_piotroski_plus_us.py`, `size_vs_liquidity_us.py`, `cost_vs_edge.py`, `daily_breakout_combo_us.py`, `roace_by_liquidity.py`, `backtest_liquidity_forward.py`.*
