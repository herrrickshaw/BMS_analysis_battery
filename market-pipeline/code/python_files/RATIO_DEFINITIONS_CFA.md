# Ratio Definitions — CFA Institute Citations

Every financial ratio computed in `factorial_screener_test.py` (functions
`compute_fundamental_screens()` and `attach_market_cap()`), cross-referenced
against its authoritative definition in Robinson, van Greuning, Henry &
Broihahn, *International Financial Statement Analysis* (CFA Institute
Investment Series, Wiley, 2009), Chapter 7 "Financial Analysis Techniques"
— the canonical source for standard ratio formulas, per the 2023 CFA Level 1
LOS ("identify, calculate, and interpret activity, liquidity, solvency,
profitability, and valuation ratios").

Status key: **MATCH** (formula identical) · **VARIANT** (a deliberate,
documented choice that differs from the textbook default, with the reason)
· **DISCREPANCY** (differs without a documented reason — worth a decision).

## Activity ratios (Exhibit 7-9, p.279)

| Code field | Formula used | CFA formula | Status |
|---|---|---|---|
| `asset_turnover` | Revenue / Total assets | Revenue / **Average** total assets | **DISCREPANCY** — see §Note below |

## Liquidity ratios (Exhibit 7-10, p.285)

| Code field | Formula used | CFA formula | Status |
|---|---|---|---|
| `current_ratio` | Current assets / Current liabilities | Current assets / Current liabilities | **MATCH** |

## Solvency ratios (Exhibit 7-11, p.289)

| Code field | Formula used | CFA formula | Status |
|---|---|---|---|
| `total_debt` | `long_term_debt + short_term_debt` (`.fillna(0)` per-component) | "we take total debt... to be the sum of interest-bearing short-term and long-term debt" (Exhibit 7-11 footnote b) | **MATCH** — this account's definition was chosen specifically to match the textbook/S&P convention |
| `de_ratio` | Total debt / Equity | Total debt / Total shareholders' equity | **MATCH** |
| `leverage` | Long-term debt / Total assets | *(no direct CFA analog — CFA's "financial leverage ratio" is Avg total assets / Avg total equity; CFA's "debt-to-assets" is TOTAL debt / total assets, not long-term only)* | **VARIANT** — a simplified long-term-debt-only leverage proxy, not one of the four named CFA solvency ratios; label reflects this (not called "debt_to_assets") |

## Profitability ratios (Exhibit 7-12, p.292)

| Code field | Formula used | CFA formula | Status |
|---|---|---|---|
| `gross_margin` | Gross profit / Revenue | Gross profit / Revenue | **MATCH** |
| `net_margin` | Net income / Revenue | Net income / Revenue | **MATCH** |
| `operating_margin` | EBIT / Revenue | Operating income / Revenue | **VARIANT** — CFA's own footnote 11 explicitly sanctions this: "Some analysts use EBIT as a shortcut representation of operating income," while flagging that EBIT technically also includes nonoperating items |
| `roa` | Net income / Total assets | Net income / **Average** total assets | **DISCREPANCY** — see §Note below |
| `roe` | Net income / Equity | Net income / **Average** total equity | **DISCREPANCY** — see §Note below |

## Valuation & credit ratios (Exhibits 7-14 p.303, 7-16 p.310)

| Code field | Formula used | CFA formula | Status |
|---|---|---|---|
| `ev_ebitda` | (Mkt cap + Total debt − Cash) / EBITDA | *(not in Exhibit 7-14's 4-ratio table — P/E, P/CF, P/S, P/B only — but standard EV/EBITDA, taught elsewhere in the CFA curriculum)* | **MATCH** to standard practice |
| `net_debt_ebitda` | (Total debt − Cash) / EBITDA | Exhibit 7-16's "Total debt to EBITDA" = **Total** debt / EBITDA (no cash netting) | **VARIANT** — deliberately uses NET debt, common in equity/credit analysis for cash-rich companies; already documented in-code as intentional (a LEVEL screen paired with `debt_reduction`, a CHANGE screen) |
| `roic` | EBIT / (Equity + Total debt − Cash) | Exhibit 7-12's "Return on total capital" = EBIT / (ST+LT debt **and equity**, no cash netting) | **VARIANT** — same net-vs-gross choice as `net_debt_ebitda`, not previously cross-referenced against the CFA exhibit until this pass |
| `pb_pass` / `ps_pass` | Mkt cap / Book value; Mkt cap / Revenue | P/B: Price/share ÷ Book value/share; P/S: Price/share ÷ Sales/share | **MATCH** (aggregate mcap-based form is algebraically identical to the per-share form) |
| `peg_ratio` | P/E ÷ (ni_growth × 100) | *(not in this CFA book's table; standard industry PEG convention — P/E ÷ growth rate expressed as a whole number)* | **MATCH** to standard practice |
| `not_distress` (Altman Z) | `1.2×(CA−CL)/TA + 1.4×RE/TA + 3.3×EBIT/TA + 0.6×MVE/TL + 1.0×Rev/TA`, distress if Z<1.81 | Identical formula and 1.81 threshold, p.311 | **MATCH — verified formula-for-formula and threshold-for-threshold** |

## Note: the one real, actionable discrepancy — average vs. ending-period denominators

The CFA text is explicit and repeated on this point (p.267-268, footnote-level
discussion): *"Because operating income occurs throughout the period, it
generally makes sense to use some average measure of assets... Most ratio
databases use a simple average of the beginning- and end-of-year balance
sheet amounts."* `roa`, `roe`, and `asset_turnover` in this codebase all use
the single **ending-period** balance sheet figure from the filing, not an
average of the current and prior filing.

This is not automatically wrong — the CFA text itself notes ending-only
assets is a real, if less common, alternative some databases use — but it's
a genuine deviation from the more standard convention, not a documented
deliberate choice the way the net-debt variants above are.

**Why this hasn't been changed yet**: `roa`/`roe`/`asset_turnover` feed
directly into several screener thresholds already calibrated against the
ending-value convention (Piotroski's `d_roa`, Magic Formula, Small-Cap
Growth's `roe>0.15` gate, Bull Cartel indirectly via `ni_growth`). Switching
to an average-based denominator would shift every one of those pass/fail
boundaries and require a full re-run + re-validation of the US v8 panel (and
every cross-market technical-only replication that shares this code) before
any result could be trusted again — the same "don't silently change a
methodology without re-validating" discipline applied throughout this
program. Flagged here as a real, open decision, not silently fixed.

## What this pass did NOT check

Chapter 6 ("Understanding the Cash Flow Statement," p.250-253) covers FCFF/
FCFE definitions in more depth than reviewed here — `fcf = cfo - capex` used
throughout this codebase is a standard FCF proxy but is closer to a
simplified "free cash flow" than the CFA's formal FCFF (which starts from
EBIT and separately adds back noncash charges, subtracts working-capital
investment and capex, and adjusts for after-tax interest) or FCFE (FCFF
further adjusted for net borrowing). Not reviewed in this pass — a candidate
for a follow-up if FCF-based screeners (`fcf_margin`, `fcf_yield`) need
tighter CFA grounding.
