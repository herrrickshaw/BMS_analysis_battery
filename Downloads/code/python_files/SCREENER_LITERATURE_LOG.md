# Screener Literature Log

Reference catalog of major stock-screening methodologies from investment literature,
cross-checked against every implementation of each one found in this codebase, with
an audit verdict and — where a genuine correctness bug was found — the fix applied.

**How this was built:** a full-codebase inventory (grep + manual read of every scan
script) found the same handful of methodologies re-implemented independently across
**~13 files** (each market-scan script, plus several report/backtest variants), and a
separate `strategies/*.py` package that in several cases encodes **materially
different logic under the same screener name**. Full literature sources are cited
per-screener below.

**Scope of fixes applied in this pass:** the files this repo's live daily pipeline
actually runs (`full_us_market_scan.py`, `full_indian_market_scan.py`,
`full_european_market_scan.py`, `daily_pipeline.sh` → `build_mailer.py`) plus the
shared `strategies/*.py` library (used by `custom_screener.py` / `screener_kit.py` /
on-demand cache regeneration, not on every daily run). Divergences found in
`full_japan_market_scan.py`, `full_korea_market_scan.py`, `us_market_screener.py`,
`us_stocks_colab.py`, `screener_analysis.py`, `backtest_screeners.py`,
`custom_screener.py`, `stock_daily_report_improved.py`, `us_stock_daily_report.py`,
`sg_stock_daily_report.py` are **documented but not edited** in this pass — those
files sit outside this branch's live pipeline and editing 8-9 near-duplicate copies
blind (without tracing each one's own call graph and callers) is a correctness risk
in itself. Treat their entries below as a map for a follow-up pass.

---

## 1. Piotroski F-Score

**Literature:** Joseph D. Piotroski, *"Value Investing: The Use of Historical
Financial Statement Information to Separate Winners from Losers"* (Journal of
Accounting Research, 2000). Nine binary tests across profitability (ROA>0, ΔROA>0,
CFO>0, CFO>NI), leverage/liquidity (Δleverage<0, Δcurrent ratio>0, no new share
issuance), and operating efficiency (Δgross margin>0, Δasset turnover>0). Score 0-9;
Piotroski's paper treats F≥8 as strong, F≤1 as weak. This codebase (and most
practitioner adaptations) use F≥7 as the "strong" cutoff.

**Implementations found:** `full_us_market_scan.py::fundamental_scan()`,
`full_indian_market_scan.py::fundamental_scan()`,
`full_european_market_scan.py::fundamental_scan()`, `strategies/piotroski.py`, +
(documented, not edited) `full_japan_market_scan.py`, `full_korea_market_scan.py`,
`us_market_screener.py::run_piotroski()`, `us_stocks_colab.py`,
`screener_analysis.py::compute_piotroski()`, `backtest_screeners.py`.

**Formula (identical in every copy):** all 9 tests match Piotroski (2000) exactly —
verified field-by-field against the paper. `F4` is coded as `(CFO/TotalAssets) >
ROA`, which is algebraically identical to the paper's `CFO > Net Income` accrual
test (ROA = NI/Assets, so dividing both sides by Assets doesn't change the
inequality) — not a deviation, just a rewritten form.

**🐛 Bug found & fixed:** every in-scope scan-file copy scores the "no dilution"
test (F7) as `(1 if sh0<=sh1 else 0) if (sh0 and sh1) else 1` — when share-count
data is missing, this **silently awards the point** rather than leaving the stock
unscored or penalizing it. That's a systematic upward F-Score bias for any name with
missing `"Share Issued"` history, common outside the US. `strategies/piotroski.py`
did the opposite (auto-fail on missing data), so the *same* stock could score
differently depending which of the two code families evaluated it.

**Fix applied:** aligned `strategies/piotroski.py`'s F7 to the scan-files'
auto-pass-on-missing convention (rather than the reverse), since that behavior is
consistent and apparently intentional across every in-scope scan file — changing 3+
production scan files' live scoring behavior for a design choice this codebase has
made consistently everywhere it appears would be a bigger, riskier change than
reconciling the one outlier module. `strategies/piotroski.py` F7 now reads:
```python
add("NoDilution", (sh <= sh_p) if (sh is not None and sh_p is not None) else True)
```

**Documented, not fixed (out of scope):** Japan/Korea additionally only compute
*Coffee Can* when a stock already has `f_strong` (Piotroski≥7) — see §2 below.

---

## 2. Coffee Can Portfolio

**Literature:** Saurabh Mukherjea, Rakshit Ranjan, Pranab Uniyal, *"Coffee Can
Investing: The Low Risk Road to Stupendous Wealth"* (2018). Buy-and-hold-10-years
philosophy for quality compounders: consistent high ROE, steady revenue growth, low
leverage, large enough to be liquid. The original screen is explicitly
**valuation-agnostic** — no P/E or DCF gate, since the philosophy is "never sell,"
not "buy cheap."

**⚠️ Found: THREE distinct criteria sets under the same name across this codebase.**

### 2a. Production scans (US: 6 criteria, ROE-based)
`full_us_market_scan.py::fundamental_scan()`: Revenue CAGR>10%, avg **ROE**>15%,
D/E<1, MCap≥$1B, no loss-making year, FCF>0 (latest year). `qualifies = all 6`.

### 2b. Production scans (India/Europe: ROCE-based, criteria count DIVERGED)
`full_european_market_scan.py::fundamental_scan()`: same 6-criterion skeleton but
uses avg **ROCE** (EBIT/(TA−CL)) instead of ROE, MCap≥€1B.
`full_indian_market_scan.py::fundamental_scan()`: same ROCE-based skeleton,
MCap≥₹500Cr, **but only 5 criteria — the FCF>0 test was missing** (`sum(cc_bits) ==
5` vs. `== 6` everywhere else).

**🐛 Bug found & fixed:** India's Coffee Can silently omitted the Free Cash Flow
check that US and Europe both have, making it a strictly easier bar to clear in
India than in any other market for the identically-named screen. Added the same
FCF>0 test (`Free Cash Flow` row, falling back to `OCF − |CapEx|` exactly like the
US/EU versions) to `full_indian_market_scan.py::fundamental_scan()`, bringing India
to parity: 6 criteria, `sum(cc_bits) == 6`.

### 2c. `strategies/coffee_can.py` — closer to Mukherjea's actual book
No market-cap floor, no "no loss year" test, no FCF test — none of which are part
of Mukherjea's original criteria. Requires ROE ≥15% in **every** year of
`roe_history` (not merely an average), which is a stricter, more literature-faithful
reading of "consistent" than the scan-files' `avg_roe > 15`. Left as-is: this is the
most philosophically-accurate implementation in the codebase and shouldn't be
diluted to match the scan-files' looser average.

**Documented, not fixed (out of scope):** `full_japan_market_scan.py` /
`full_korea_market_scan.py` only compute Coffee Can *if* the stock already passed
Piotroski≥7 — a scope gate absent from US/India/Europe, meaning a stock that would
pass Coffee Can on its own merits but has F<7 is never evaluated for it in
Japan/Korea. `backtest_screeners.py`'s D/E fallback has no balance-sheet computation
when `info.debtToEquity` is missing (every production scan does), making the
backtest systematically stricter than the scans it's meant to approximate.

---

## 3. Magic Formula

**Literature:** Joel Greenblatt, *"The Little Book That Beats the Market"* (2005).
Rank the entire investable universe by Earnings Yield (EBIT/EV) and Return on
Capital (EBIT/(Net Working Capital + Net Fixed Assets)), sum the two ranks, buy the
top ~20-30 by combined rank. **It is a cross-sectional ranking system, not a
fixed-threshold pass/fail test** — every implementation in this codebase (including
the fixed one below) is a threshold simplification of the true method; this is
inherent to running it per-stock rather than per-universe and is called out rather
than "fixed," since doing it properly would require restructuring the caller to rank
across the whole scan result, not just this one function.

**Implementations found:** `full_us_market_scan.py`, `full_indian_market_scan.py`
(ROIC>25%, EY>15%, book value>0, market-cap floor — explicitly cited in
`screener_analysis.py`'s docstring as "matching screener.in"), `strategies/
magic_formula.py` (ROC≥15%, EY≥8%, **no** market-cap or book-value gate), +
(documented, not edited) `backtest_screeners.py` (explicitly self-documented in its
own comments as "relaxed" thresholds for statistical power: ROIC>15%, EY>8%,
mcap>₹100Cr).

**🐛 Inconsistency found & fixed:** `strategies/magic_formula.py`'s thresholds
(EY≥8%, ROC≥15%) were roughly half the production scans' (EY>15%, ROIC>25%, the
values sourced from screener.in) and had no market-cap or book-value sanity gate at
all — a stock could pass this module's "Magic Formula" and fail every production
scan's, or vice versa, for the identical company on the identical day. Reconciled
`strategies/magic_formula.py` to the production-scan thresholds and added the
book-value>0 gate:
```python
EY_MIN = 15.0    # was 8.0
ROC_MIN = 25.0   # was 15.0
# + book_value > 0 required, matching full_us/full_indian_market_scan.py
```
Capital-employed formula caveat (not changed — see below): Greenblatt's denominator
is specifically Net Working Capital + Net Fixed Assets, deliberately **excluding**
goodwill/intangibles so acquisition premiums don't distort the capital base. Every
scan-file implementation instead uses `Total Assets − Current Liabilities`
("capital employed"), which is broader (includes goodwill/intangibles/other
long-term assets). This documented as a known literature deviation rather than
"fixed," since correctly excluding goodwill needs a `Goodwill And Other Intangible
Assets` line yfinance doesn't reliably expose for every ticker — a wrong fix here
(mis-parsing that field for some tickers) would be worse than the current, at-least-
consistent approximation.

---

## 4. Darvas Box

**Literature:** Nicolas Darvas, *"How I Made $2,000,000 in the Stock Market"*
(1960). A stock forms a "box" — a period where price consolidates between a
confirmed resistance (box top) and support (box bottom) for several consecutive
days without breaking either. Buy on a breakout above the box top; the stop-loss
sits just below the box bottom and trails upward as new, higher boxes form; exit on
a breakdown below the current box bottom.

**Implementations found (all functionally identical, correct box-detection
algorithm):** `full_us_market_scan.py::compute_darvas_box()`,
`full_indian_market_scan.py::compute_darvas_box()`,
`full_european_market_scan.py::compute_darvas_box()`, `darvas_breakouts.py`, +
(documented, not edited) `full_japan_market_scan.py`, `full_korea_market_scan.py`,
`us_market_screener.py`, `us_stocks_colab.py`, `screener_analysis.py`,
`stock_daily_report_improved.py`, `us_stock_daily_report.py`,
`sg_stock_daily_report.py`, `backtest_screeners.py::detect_darvas_signals()` (a
walk-forward no-lookahead variant with an added 20%-above-20-day-average volume
confirmation and a 10-bar cooldown between signals — a deliberately stricter
backtest-safe variant, not a bug).

**Formula (verified against every in-scope copy):** current bar excluded from box
formation (no lookahead); box top = a high with the next `confirm=3` bars' highs all
strictly lower; box bottom = from the box-top index forward, a low with the next 3
bars' lows all strictly higher (falls back to segment min if none found);
`BREAKOUT_BUY` if price > box top, `BREAKDOWN_SELL` if price < box bottom. This is a
faithful, literature-accurate box-detection algorithm and is consistent across every
in-scope file.

**🐛 Bug found & fixed:** `strategies/darvas.py`, despite being named "Darvas Scan"
(slug `darvas`) and its docstring claiming "Darvas box breakout," implemented a
**completely different methodology with no box detection at all** — just "price
within 10% of the 52-week high AND today's volume ≥1.5× the 20-day average." Any
caller using `screener_kit.screen("darvas", ...)` was getting a generic momentum
screen mislabeled as Darvas, not Nicolas Darvas's actual method — and would produce
systematically different results from every other "Darvas" screen in this codebase.

**Fix applied:** rewrote `strategies/darvas.py::screen()` to use the same
box-detection algorithm as the rest of the codebase (box top/bottom via the
3-bar-confirmation method, `BREAKOUT_BUY`/`BREAKDOWN_SELL`/`IN_BOX` classification),
adapted to the `StockData`/`Result` contract. It now reports `Box_Top`, `Box_Bottom`,
`Position_in_Box%`, and `Upside_to_Top%` — the same fields every other Darvas
implementation in the codebase produces — instead of a near-high/volume proxy.

---

## 5. Golden Cross / Death Cross

**Literature:** Classic technical-analysis trend-following signal — the 50-day
moving average crossing above (Golden Cross, bullish) or below (Death Cross,
bearish) the 200-day moving average. No single academic paper originates it; it's
standard technical-analysis practice (see e.g. John Murphy, *"Technical Analysis of
the Financial Markets"*).

**Implementations found:** `full_us_market_scan.py::compute_golden_crossover()`,
`full_indian_market_scan.py::compute_golden_crossover()`,
`strategies/golden_crossover.py`, `build_mailer.py::_market_snapshot_html()`
(added earlier this session — the daily brief's 50/200-DMA snapshot banner) +
(documented, not edited) `screener_analysis.py`.

**Verdict: correct, no divergence.** Every copy checks a genuine crossover event
(yesterday's 50-DMA was below 200-DMA, today's is above), not merely "currently
above," which is the literature-correct definition. `strategies/golden_crossover.py`
requires a slightly larger data buffer (205 vs 201 bars) — cosmetic, not a
correctness issue.

**Scope note (not a bug):** Europe/Japan/Korea market scans have no Golden Cross
screener at all — only Darvas + fundamentals — so those markets' "Triple Hit"
composition never includes a trend-confirmation leg that US/India get. Worth knowing
if comparing Triple Hit counts across markets, not something to silently "fix"
without deciding whether Golden Cross belongs in those markets' methodology.

---

## 6. Bull Cartel (quarterly momentum overlay)

**Literature note:** this is **not** a textbook/academic screener — "Bull Cartel"
appears to be informal Indian retail-trading terminology (a proxy for
institutional/promoter accumulation via strong quarter-over-quarter growth), not a
citable methodology from investment literature. Documented here for completeness
since it's one of the 4 screeners run on every stock, not because it traces to a
published source.

**Implementations found:** `full_us_market_scan.py`, `full_indian_market_scan.py`,
+ (documented, not edited) `backtest_screeners.py`.

**Formula:** YoY quarterly comparison (latest quarter vs. 4-quarters-ago, i.e.
same-season last year): sales growth >15%, profit growth >20%, net profit above a
per-market floor ($1M US / ₹1Cr India). **Verdict: correct, no divergence** — the
only difference across markets is currency-scale localization, which is intentional.

---

## 7. Cash Conversion Cycle (CCC)

**Literature:** Richard Lawrence, working-capital efficiency concept popularized in
corporate finance textbooks (e.g. Brealey/Myers/Allen, *"Principles of Corporate
Finance"*). `CCC = DIO + DSO − DPO` where DIO = Inventory/COGS×365, DSO =
Receivables/Revenue×365, DPO = Payables/COGS×365. Lower/negative CCC = the company
collects from customers before it has to pay suppliers (funds growth with float).

**Implementations found:** `screener_in.py::ccc_screen()` (live-scrapes
screener.in's own precomputed screen at screens/228040 — a *data source*, not an
independent formula; **fixed earlier this session** — see the git history for the
Liquidity-column bug that silently made this section always render "n/a"),
`strategies/cash_conversion_cycle.py` (computes DIO+DSO−DPO from raw fundamentals
directly, `CCC_MAX=45` days pass threshold), `custom_screener.py::_ccc()` (same
formula, no fixed threshold — left to the caller). **Verdict: formula correct and
consistent** across both from-scratch implementations; verified against the
textbook definition field-by-field.

**Also added this session:** `test_screener_in.py` — a daily data-quality tripwire
for the screener.in scrape (non-empty, required columns present, values in a
plausible range), wired into `daily_pipeline.sh` step `[3c]`.

---

## 8. GARP (Growth at a Reasonable Price)

**Literature:** Peter Lynch, *"One Up on Wall Street"* (1989) — the PEG ratio
(P/E ÷ earnings growth rate) as the primary GARP filter; PEG≤1 signals growth priced
reasonably relative to the multiple paid.

**Implementation found:** `strategies/garp.py::screen()` (only implementation in
the codebase).

**🐛 Bug found & fixed:** the "reasonable" gate was `(PEG≤1) OR (PE≤industry_PE) OR
(PE≤40)` — three OR'd conditions — but `passed` *also* separately required `PE≤40`
as an outer condition. Since the third OR-branch is just `PE≤40` again, "reasonable"
was **true whenever the outer PE≤40 ceiling was already satisfied**, regardless of
whether PEG or industry-PE passed. In practice this meant a stock with, say, PE=35
and growth=15% (PEG=2.33 — clearly not GARP by Lynch's own PEG≤1 standard) would
still pass, because `PE≤40` alone satisfied "reasonable." The PEG≤1 test the
module's own docstring calls "the classic Lynch test" was almost never the binding
constraint.

**Fix applied:** removed the redundant `(pe <= PE_MAX)` disjunct from the
`reasonable` gate — it remains only as the hard outer ceiling. `reasonable` is now
`(PEG≤1) OR (PE≤industry_PE)`, so a stock must actually clear one of the two
substantive quality-of-price tests, not just the generic sanity cap:
```python
reasonable = (peg is not None and peg <= PEG_MAX) or \
             (industry_pe is not None and pe <= industry_pe)
# (pe <= PE_MAX) removed from here — it's already enforced as the outer ceiling below
passed = growth >= GROWTH_MIN and reasonable and pe <= PE_MAX
```

---

## 9. Dividend Yield / "Dogs of the Dow" family

**Literature:** John Slatter / Michael O'Higgins, *"Beating the Dow"* (1991) — the
"Dogs of the Dow" strategy of buying the highest-yielding blue chips. This codebase
implements a simplified, single-market version (highest current yield among
consistent payers), not the full annual-rebalance-within-one-index strategy.

**Implementation found:** `strategies/dividend_yield.py::screen()` (only
implementation). Yield≥2%, paid a dividend in ≥3 of the recent years. **Verdict:
correct for what it claims to be** (a simplified consistent-yield screen); no
cross-file divergence since there's only one copy.

---

## 10. Debt Reduction (deleveraging + capacity expansion)

**Literature:** not a single named academic screen — a composite "quality
turnaround" heuristic (steadily falling debt while capex/gross block rises,
signaling self-funded deleveraging rather than a forced fire-sale of assets),
consistent with the deleveraging-quality factor literature (e.g. Novy-Marx's
"quality" factor work touches on this general idea, though this specific
combination isn't from one paper).

**Implementation found:** `strategies/debt_reduction.py::screen()` (only
implementation).

**🐛 Dead code with inverted logic, removed:** the module defined a helper
`_decreasing(series)` that was **never called anywhere** — the actual `screen()`
function has its own separate, correctly-implemented inline check
(`all(a < b for a, b in zip(debt_vals, debt_vals[1:]))`, which correctly identifies
falling debt in a newest-first list). The unused `_decreasing()` helper's own logic
was inverted relative to its own docstring comment (it would return `False` for
genuinely falling debt). Since it was dead code, it wasn't producing wrong live
results, but it's a landmine for anyone who wires it in later. Removed.

---

## 11. Loss to Profit Turnaround

**Literature:** special-situations / turnaround investing, in the tradition of Joel
Greenblatt's *"You Can Be a Stock Market Genius"* (1997) — companies transitioning
from net loss to net profit are a classic special-situation catalyst, though
Greenblatt's book is broader (spin-offs, restructurings) than this specific
sign-flip test.

**Implementation found:** `strategies/loss_to_profit.py::screen()` (only
implementation). Prior-quarter loss (any of the trailing 3) + current-quarter
profit. **Verdict: correct, no divergence.**

---

## 12. Bluest of the Blue Chips

**Literature note:** India-specific practitioner/screener.in community terminology
(large-cap quality-at-reasonable-price composite), not a single citable academic
source — analogous in spirit to Buffett/Munger's "wonderful business at a fair
price" heuristic but without a specific formula from their writings.

**Implementation found:** `strategies/bluest_blue_chips.py::screen()` (only
implementation). MCap≥₹3000Cr, profit growth≥10%, ROE≥15%, PE≤industry PE (or PE>0
if industry PE unavailable). **Verdict: internally consistent, no cross-file
divergence** — flagging one design pattern for awareness: when `industry_pe` is
unavailable, the valuation leg defaults to **pass** rather than fail (same
missing-data-defaults-to-pass pattern seen in Piotroski F7 and GARP's industry-PE
branch). Not changed — this is a repeated, apparently deliberate design convention
in this codebase's `strategies/` package, not a one-off accident.

---

## Screeners cataloged for reference (not currently implemented in this codebase)

Documented here so a future addition has a literature citation on file, per the
"20+ major screeners" scope of this audit — these are not coded anywhere in this
repo today:

- **Benjamin Graham — Defensive Investor** (*The Intelligent Investor*, 1949/1973):
  adequate size, current ratio≥2, 10y positive earnings, 20y uninterrupted dividends,
  10y EPS growth≥33%, P/E≤15, P/B≤1.5 (or P/E×P/B≤22.5).
- **Benjamin Graham — Net-Net (NCAV)**: price < ⅔ × (Current Assets − Total
  Liabilities). Deep-value, classically the strongest-performing Graham screen in
  academic replications.
- **Graham Number**: intrinsic-value ceiling = √(22.5 × EPS × Book Value/share).
- **Altman Z-Score** (Edward Altman, 1968): bankruptcy-risk composite —
  `Z = 1.2(WC/TA) + 1.4(RE/TA) + 3.3(EBIT/TA) + 0.6(MVE/TL) + 1.0(Sales/TA)`.
  Z>2.99 safe, 1.81-2.99 grey zone, <1.81 distress.
- **CANSLIM** (William O'Neil, *How to Make Money in Stocks*): Current-quarter
  earnings≥25% YoY, Annual growth≥25%/3y, New catalyst, Supply/demand (buybacks, low
  float), Leader (relative strength≥80), Institutional sponsorship, Market direction.
- **Quality Minus Junk / QMJ** (Asness, Frazzini, Pedersen, AQR 2013): composite
  rank of profitability + growth + safety (low leverage/earnings volatility) +
  payout; long quality, short junk.
- **Altman-adjacent: Beneish M-Score** (Messod Beneish, 1999): earnings-manipulation
  detection composite; M>-1.78 flags manipulation risk.
- **Dividend Aristocrats**: S&P criterion of 25+ consecutive years of dividend
  increases, typically screened with payout ratio<60%.
- **Free Cash Flow Yield**: FCF/Enterprise Value above a threshold (commonly 5-8%)
  as a cheap-and-cash-generative screen, distinct from the earnings-yield leg of
  Magic Formula.
- **PEAD (Post-Earnings-Announcement Drift)**: momentum continuation after an
  earnings surprise — flagged in this session's memory as a "novel real screen to
  port" from other repos surveyed, not yet built here.

---

## Summary of fixes applied this session

| File | Fix |
|---|---|
| `strategies/darvas.py` | Rewrote to use real Darvas Box detection (was a near-52w-high+volume proxy with no box logic at all) |
| `strategies/garp.py` | Removed the redundant `PE≤40` disjunct that made the PEG/industry-PE "reasonable" gate vacuous |
| `strategies/piotroski.py` | Aligned F7 (no-dilution) missing-data default to auto-pass, matching every production scan file |
| `strategies/magic_formula.py` | Reconciled EY/ROC thresholds to the production-scan (screener.in-sourced) values; added book-value>0 gate |
| `strategies/debt_reduction.py` | Removed dead, unused helper with inverted logic |
| `full_indian_market_scan.py` | Added the missing FCF>0 Coffee Can criterion (was 5/6 criteria vs. 6/6 in US/Europe) |

Everything else above with a "documented, not edited" marker is a real, verified
finding — just outside this session's scope (files not touched by this branch's live
daily pipeline). Treat those entries as the starting map for a follow-up pass.
