# Liquidity, Not Size, Conditions the Piotroski F-Score Premium

### Evidence from US equities, 2016–2026, with point-in-time filing dates

**Research note · 15 July 2026 · Educational and research use only. Not investment advice.**

---

> ## STATUS: regenerated on clean data (15 Jul 2026, final)
>
> Adversarial validation (five agents, each instructed to *refute*) found **eight defects**
> after the first draft. All the data defects are now fixed and every number below is from
> the clean re-collection. **The corrections shrank the findings; none grew.**
>
> | defect | resolution |
> |---|---|
> | US `revenue` stored the ASC-606 *subset* — ADM FY2023 held $25.69B vs a 10-K ~$93.9B | **Fixed.** `Revenues` now takes tag precedence. |
> | `form=10-K AND fp=FY` **does not mean annual** — a 10-K tags its quarterly breakouts `fp=FY`, so quarters entered the series as fiscal years | **Fixed** by a duration filter (300–400 days). **This removed 61,236 rows — half the dataset.** `revenue_suspect` fell 19,044 → 640. ADM 2023 is now one row at $93.94B. |
> | US price panel was an **interrupted alphabetical collection** (CME, Cummins, all of D–L absent) | **Fixed.** Coverage 13% → 43% of tickers. |
> | Per-market liquidity floors were **fabricated** (US $475k reproduced under no definition) | **Fixed by deletion.** Only India's ₹1cr — a policy a human actually chose — remains. |
> | `(x or 0)` silently keeps NaN (`float(str(nan))` succeeds; NaN is truthy) | **Fixed.** |
> | `EBIT = PBT + interest` is **wrong for lenders**; errors cancel *into* the plausible band so no range check fires | **Fixed** via screener.in's sector field, after three ratio/structure detectors were refuted. |
>
> Two of the four double-sort cells are now classified **unmeasured** — see §4.1. That is a
> result, not an omission.

---

## Abstract

We test whether the Piotroski (2000) F-score premium is conditioned by firm size or by
stock liquidity — two attributes that are heavily entangled and are routinely conflated.
Using SEC EDGAR fundamentals gated on **actual filing dates** and a survivorship-complete
price panel, we find the F-score premium tracks **illiquidity, not size**. Double-sorting
liquidity within size, illiquid names out-earn liquid names in *both* size buckets, and
the largest premium (**+29.3pp median**) appears in **large-capitalisation but illiquid**
firms — not small caps. That cell was measured five times as data defects were fixed and
landed in 27.8–33.7 every time, surviving a corruption that removed half the dataset.
Two of the four cells are classified **unmeasured**: they moved monotonically with every
input fix and never converged.

We separately confirm Fang, Noe & Tice (2009): return on capital employed rises
monotonically with liquidity (11.0% → 21.6% ex-cash). Better companies are more liquid;
better *investments* are not. A Corwin–Schultz + Amihud cost model bounds the strategy's
capacity at roughly **$250k**, set by execution rather than fees — consistent with the
F-score literature's finding that the premium is unreachable at institutional scale.

We report **eleven** derived metrics that failed validation, every one caught by an
independent check and none by reasoning; three more were fixes proposed here that the data
refuted before they shipped. Mean and median disagreed on **every** headline result, with
the median correct each time. **Every finding shrank as the inputs were cleaned; none
grew** — which is the note's most useful result.

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
| **Fundamentals** | SEC EDGAR, 5,016 tickers, 62,939 annual rows (after the duration filter removed 61,236 quarterly rows) |
| **Prices** | 10.5y point-in-time panel, 9,278 symbols (the complete one — an earlier panel was an interrupted alphabetical collection) |
| **Usable panel** | 11,955 stock-years · 2,028 symbols · 9 annual rebalances (2017–2025) |
| **Coverage** | 43% of EDGAR tickers, up from 13% once the broken panel and an inconsistent field requirement were fixed |

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
measurable. Their rank correlation is **+0.236** (n=288), **+0.239** (n=150) and **+0.172**
(n=~150) across three independent samples: they are complements, not substitutes. That
reproducibility — three samples, all near +0.2 — makes it the note's most stable finding,
more so than any premium estimate.

Returns are winsorised 1/99 per rebalance. **Median is the headline throughout.**

## 4. Results

### 4.1 The premium tracks illiquidity, not size

Turnover and market capitalisation correlate at **+0.797**. Ranking on turnover alone —
as we initially did — cannot distinguish them. Double-sorting liquidity *within* size,
with capitalisation measured point-in-time (last close × shares as filed):

| Size | Liquidity | n | F≥70 | F<40 | **Premium** | @818 | @1,673 | @2,703 | contam. |
|---|---|---|---|---|---|---|---|---|---|
| Small | Illiquid | 2,967 | −1.4% | −10.1% | **+8.7pp** | +13.8 | +12.2 | +13.4 | +9.4 |
| Small | Liquid | 2,967 | +4.9% | −1.1% | +6.0pp | +7.7 | +13.9 | +7.5 | +5.8 |
| **Large** | **Illiquid** | 2,967 | +5.5% | **−23.9%** | **+29.3pp** | +33.7 | +27.8 | +31.4 | +29.2 |
| Large | Liquid | 2,967 | +8.1% | −3.1% | +11.2pp | −1.7 | +3.6 | +7.4 | +10.6 |

**The prior-run columns are the most important part of this table.** The same four cells
were measured five times as data defects were fixed. They did not behave alike, and the
difference is what separates a finding from an artefact.

**`LARGE + ILLIQUID` is the finding.** Five measurements, every one in **27.8–33.7**, and it
survived a corruption that removed *half* the dataset. Its mechanism is intact throughout:
weak-F names there crash **−23.9%**.

**The thesis holds, narrowly.** Illiquid beats liquid in both size buckets — but Small's gap
shrank from +6.1pp to **+2.7pp** as the data cleaned.

**Two cells are UNMEASURED, and we say so rather than quoting them:**

- **Small+Illiquid fell monotonically** with every fix: 13.8 → 12.2 → 13.4 → 9.4 → **8.7**.
  Contamination was inflating it.
- **Large+Liquid climbed monotonically across all five**: −1.7 → +3.6 → +7.4 → +10.6 → **+11.2**,
  never converging. An earlier draft called it *"the only negative cell"* at −1.7. It is now
  +11.2 and still moving. **A quantity that moves with every input fix has not been
  measured** — it has been sampled from a distribution we cannot yet pin down. This
  conclusion was committed to *before* the final run, precisely so it could not be
  rationalised after.

A claim that survives a 3.3× increase in sample is worth more than one that doesn't. Two
of these four did; two did not. The thesis rests on the two that did.

**Mechanism.** In the strongest cell, illiquid large-caps with weak fundamentals *crash*
(F<40 median −23.9%): value traps, low float, distressed names institutions cannot exit.
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
