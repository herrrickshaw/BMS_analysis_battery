# ASSUMPTIONS.md

Reasonable assumptions made during implementation. Documented here so future contributors know the why behind approximations.

---

## Data Source

**Screener.in snapshot exports** — all three scans operate on single-point-in-time data. Screener.in does not export full annual time-series per stock in its standard CSV query. This means:

- YoY comparisons (Piotroski F3, F5, F7) cannot be computed from a single export.
- "10-year" Coffee Can ROCE is approximated from the TTM/current ROCE.
- Where a multi-year field is missing, the criterion is marked **N/A** and excluded from the score denominator.

---

## Darvas Box

| Assumption | Rationale |
|---|---|
| **Box floor = 85% of 52W High** | True Darvas boxes need weekly OHLCV history. 85% of the 52W High approximates a 15% box range, consistent with Darvas's original method. |
| **"New 52W high in last 10 sessions"** — approximated as CMP within 3% of 52W High | Screener exports the 52W High but not the date it was set. CMP ≤ 3% below the 52W High is a strong proxy for a recent breakout. |
| **Volume breakout** — `Volume / 30D Avg Volume ≥ 1.5×` | Standard Darvas filter. If either volume column is missing the criterion is skipped (N/A). |
| **Sector P/E fallback = 35** | If Sector PE is not in the export, absolute P/E < 35 is used as the Buffett valuation screen. Covers most Indian growth sectors; change in `scanners/darvas.py` if needed. |
| **Promoter holding > 50%** for Indian stocks | Buffett's insider ownership proxy for Indian markets. For NASDAQ ADRs this criterion may score N/A since Screener does not export US insider % in the same column. |

---

## Piotroski F-Score

| Criterion | Status | Assumption |
|---|---|---|
| F1 ROA > 0 | Computed | ROA = Net Profit / Total Assets × 100, or uses `ROA %` column directly |
| F2 OCF > 0 | Computed | Uses `Cash from Operations` column |
| F3 ROA improving YoY | **Skipped** | Requires two periods of ROA; not available in a snapshot export |
| F4 Low accruals | Computed | Pass when OCF/Assets > ROA (cash earnings exceed reported earnings) |
| F5 LT debt decreased | **Approximated** | D/E < 0.5 used as proxy; actual YoY comparison not possible from snapshot |
| F6 Current ratio improved | **Approximated** | Current Ratio > 1.5 used; actual prior-year value not available |
| F7 No share dilution | **Skipped** | Requires share count history not in standard Screener export |
| F8 Gross margin improved | **Approximated** | Operating Profit Margin > 20% used as proxy |
| F9 Asset turnover improved | **Approximated** | Asset Turnover > 0.5, or ROE > 15% if AT column missing |

**Pre-computed Piotroski score**: If the Screener.in export includes a `Piotroski score` column, it is used directly and overrides computed sub-scores. Screener.in computes the full 9-point score with historical data — this is more accurate than the snapshot approximation.

---

## Coffee Can Portfolio

| Assumption | Rationale |
|---|---|
| **Revenue CAGR source priority**: 10Y → 5Y → 3Y | Use the longest available period. Most Screener exports have 3Y and 5Y; 10Y is rarer. |
| **ROCE check** — single TTM ROCE compared against 15% threshold | True Coffee Can requires ROCE > 15% **every single year** for 10 years. Screener snapshot only provides TTM ROCE. Accept this as a conservative pass (if TTM fails, the stock fails; if TTM passes, it's a necessary but not sufficient condition). |
| **CFO/PAT criterion** — not computed | Requires 10-year annual OCF and PAT series. Omitted; reflected in lower completeness %. |
| **Market cap > ₹100 Cr** | Lower bound for Indian stocks. For NASDAQ ADRs the same number threshold is applied to USD Market Cap (USD M) which means effectively $100M+. |
| **Promoter pledge < 10%** — marked N/A if column missing | Many Screener exports omit this. When missing, governance risk is noted via completeness score rather than failing the stock. |
| **Gross margin > 40% for moat** | Uses Operating Profit Margin as proxy for gross margin since Screener does not always separate the two. |
| **Revenue concentration risk** | Not computed — requires notes/AR data not available in CSV exports. |

---

## General

| Assumption | Rationale |
|---|---|
| **In-memory data store** | Each market's DataFrame lives in server memory for the session. Restarting the backend clears all uploaded data. Acceptable for a single-user research tool; add a DB layer for multi-user production. |
| **NASDAQ ADR column mapping** | Sample file uses different header names (e.g. "Price (USD)" instead of "CMP Rs.") to demonstrate the column mapper. The mapper handles 40+ header variations per field. |
| **Banks / NBFCs** | Naturally have D/E > 1 (financial leverage) and no meaningful current ratio. Coffee Can will AVOID most banks. Piotroski F5 (low leverage proxy) will also penalise banks. This is intentional — Coffee Can is not designed for financials. |
| **Missing columns** | Any criterion with a missing input column returns `null` (displayed as grey dot) and is excluded from score and max-score. Data completeness % reflects how many required fields were found. |
| **Python 3.9 compatibility** | Backend uses `from __future__ import annotations` and `Optional[T]` to support Python 3.9+. Tested on 3.9 and 3.11. |
