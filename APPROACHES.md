# The Two Analytical Approaches

This system analyses every stock through **two independent lenses** and reports
them as two labelled components in the daily mailer, plus a convergence highlight.

> ⚠️ Educational/research only. Convergence is NOT a buy signal. NOT investment advice.

---

## 1. Fundamental / Historical Approach

**Pipeline:** `pipeline_historical.py` → `daily_combined_report.py` Component 1
**Question it answers:** *"Is this a structurally sound stock by its own numbers?"*

| Aspect | Detail |
|---|---|
| **Data** | 5-year OHLC + annual/quarterly financials (Parquet cache, **offline**) |
| **Tools** | 6 screeners, each an objective rule (Specification): Darvas Box, Golden Cross, Piotroski F-Score, Coffee Can, Magic Formula, Bull Cartel |
| **Output** | "Stock Picks Based on Fundamentals" — the deduplicated union of every stock passing ≥1 screener, tiered Triple Hit > Multi-Screen > Single-Screen |
| **Nature** | Deterministic, repeatable, **backtestable** — a stock either clears a numeric threshold or it doesn't |
| **Strength** | No look-ahead, no third-party text, fully reproducible from cached data |
| **Limitation** | Backward-looking; says nothing about *today's* catalysts |

**Verified behaviour:** backtests show fundamental screeners (Bull Cartel, Piotroski)
earn the strongest expected value in BEAR regimes; Darvas works best as a
confirmation filter; the full system surfaces ~1,225 unique Indian picks.

---

## 2. News / Sentiment Approach

**Pipeline:** `pipeline_news.py` → `daily_combined_report.py` Component 2
**Question it answers:** *"What is the market saying about this stock right now?"*

| Aspect | Detail |
|---|---|
| **Data** | Live headlines (**online**) — RSS: Moneycontrol/ET/BusinessLine/LiveMint (IN), CNBC/MarketWatch (US); + optional Marketaux/AlphaVantage/Finnhub/NewsData APIs |
| **Tools** | News providers → **company-name** matching (via `symbol_master.parquet`) → VADER (finance-tuned) or provider-native sentiment |
| **Output** | "Talk on the Street" — per-stock sentiment + a market-mood regime gauge |
| **Nature** | Forward-looking, **noisy**, fast-moving — not backtestable |
| **Strength** | Captures catalysts (results, upgrades, deals) the price may not have fully reflected |
| **Limitation** | Provider-dependent; can lead OR lag price; sentiment scores are directional, sometimes mis-signed (e.g. VADER read "stock slides 12%" as positive) |

**Key design:** matching is on the **company name**, not the ticker — so "Reliance
Industries" matches RELIANCE and "Adani Enterprises" ≠ "Adani Ports". This fixed
both recall (headlines use names) and precision (no DEN↔"dent" substring hits).

---

## Convergence — the cross-check

A stock appears in the **Convergence** section when both approaches agree:

- **✅ Both bullish** — fundamentally screened AND positive news → highest conviction
- **⚠️ Caution** — fundamentally strong BUT negative news → review before acting

Because the two approaches have *different failure modes* (fundamentals miss
catalysts; sentiment is noisy), their agreement is a useful **cross-check** — but
explicitly **not a buy signal**. The daily mailer leads with this section.

---

## Extending either approach with minimal code

`tool_registry.py` turns "add a new tool" into one decorated function:

```python
from tool_registry import screener, news_source, analysis

# New fundamental screener — ~5 lines, auto-discovered by the scan loop
@screener("high_roe", "ROE > 20%")
def high_roe(c):
    roe = c._row(c.income_stmt, "Net Income") / (c.book_value or 1e9)
    return bool(roe and roe > 0.20)

# New news source — just give it RSS feeds
@news_source("reuters_in", feeds=["https://.../reuters_india.rss"], market="IN")
def _(): ...

# New analysis stage — appears in pipeline_historical --stages
@analysis("momentum_rank")
def momentum_rank(ohlc_map): ...
```

The scan/report pipelines iterate `run_all_screeners(candidate)` instead of
hard-coding each rule, so the registry is the single source of truth and the
codebase stays short as capabilities grow.

See [GLOSSARY.md](GLOSSARY.md) for term definitions and
[STOCK_ANALYSIS_SYSTEM.md](STOCK_ANALYSIS_SYSTEM.md) for full methodology.
