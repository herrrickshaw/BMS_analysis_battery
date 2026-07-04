- 👋 Hi, I'm Umashankar
- 👀 I'm interested in machines that are learning
- 🌱 I'm currently learning about said machines
- Humans have always complained that they are being worked like a machine, then why don't machines do that work?
- 💞️ I'm looking to collaborate on topics of common interest such as fluid modelling, financial modelling, token economics and teaching machines context
- 📫 How to reach me, message on Github

---

# Global Ticker Universe

**60,971 validated tickers across 25 markets** — cross-referenced against FinanceDatabase, deduplicated and filtered for active listings.

| Market | Tickers | Exchange | Source |
|---|---|---|---|
| 🇩🇪 Germany | 17,121 | Xetra + Frankfurt | FinanceDatabase validated |
| 🇦🇹 Austria | 8,813 | Vienna Stock Exchange | FinanceDatabase validated |
| 🇺🇸 United States | 6,443 | NYSE / NASDAQ / AMEX | FinanceDatabase validated |
| 🇨🇳 China | 3,431 | SSE + SZSE | FinanceDatabase validated |
| 🇮🇳 India | 2,984 | NSE / BSE | FinanceDatabase validated |
| 🇧🇷 Brazil | 2,755 | B3 | FinanceDatabase validated |
| 🇬🇧 United Kingdom | 2,713 | LSE | FinanceDatabase validated |
| 🇯🇵 Japan | 2,658 | TSE | FinanceDatabase validated |
| 🇮🇹 Italy | 2,249 | Borsa Italiana | FinanceDatabase validated |
| 🇫🇷 France | 2,050 | Euronext Paris | FinanceDatabase validated |
| 🇦🇺 Australia | 1,657 | ASX | FinanceDatabase validated |
| 🇭🇰 Hong Kong | 1,473 | HKEX | FinanceDatabase validated |
| 🇸🇪 Sweden | 1,146 | Nasdaq Stockholm | FinanceDatabase validated |
| 🇳🇴 Norway | 1,004 | Oslo Børs | FinanceDatabase validated |
| 🇨🇦 Canada | 779 | TSX | FinanceDatabase validated |
| 🇹🇼 Taiwan | 664 | TWSE | FinanceDatabase validated |
| 🇩🇰 Denmark | 643 | Nasdaq Copenhagen | FinanceDatabase validated |
| 🇰🇷 South Korea | 545 | KRX | FinanceDatabase validated |
| 🇦🇷 Argentina | 442 | BYMA | FinanceDatabase validated |
| 🇿🇦 South Africa | 391 | JSE | FinanceDatabase validated |
| 🇷🇺 Russia | 242 | MOEX | FinanceDatabase validated |
| 🇸🇦 Saudi Arabia | 154 | Tadawul | FinanceDatabase validated |
| 🇳🇿 New Zealand | 137 | NZX | FinanceDatabase validated |
| 🇨🇭 Switzerland | 132 | SIX | FinanceDatabase validated |
| 🇪🇸 Spain | 106 | BME | FinanceDatabase validated |

> Data as of July 2026. Validated using FinanceDatabase cross-reference. Full list: [`data/validated_universe_flat.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/validated_universe_flat.csv)

---

# German Market — Eurex Derivatives Universe

Live data sourced from the **Eurex T7 GraphQL API** (Deutsche Börse, as of 2026-07-03).

| Tier | Count | Criteria |
|---|---|---|
| All Eurex single-stock listings | 1,497 | SSF / SSO / TRF / Dividend Futures |
| Optionable + Futures (institutional) | 108 | Has both SSO and SSF listed |
| Coffee Can PASS | 37 | 3 or 4 derivative types listed |
| PEGU Grade A+ / A | 11 | Score ≥ 70, full ecosystem |
| DAX 40 members covered | 163 | Eurex product codes for DAX constituents |

**Top German stocks by PEGU score:**

| Stock | PEGU Score | Grade | Tier | DAX 40 |
|---|---|---|---|---|
| SAP SE | 98 | A+ | OPTIONABLE_FUTURE | ✓ |
| E.ON SE | 85 | A+ | OPTIONABLE_FUTURE | ✓ |
| BMW AG | 75 | A | OPTIONABLE_FUTURE | ✓ |
| Mercedes-Benz Group | 70 | A | OPTIONABLE_FUTURE | ✓ |
| Allianz SE | 65 | B+ | OPTIONABLE_FUTURE | ✓ |
| Continental AG | 65 | B+ | OPTIONABLE_FUTURE | ✓ |
| Deutsche Post AG | 65 | B+ | OPTIONABLE_FUTURE | ✓ |
| Siemens AG | 65 | B+ | OPTIONABLE_FUTURE | ✓ |
| Infineon Technologies | 65 | B+ | OPTIONABLE_FUTURE | ✓ |

Raw Eurex data files: [`data/eurex_products.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/eurex_products.csv) · [`data/german_pegu_scored.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/german_pegu_scored.csv) · [`data/eurex_pegu_all_europe.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/eurex_pegu_all_europe.csv)

---

# PEGU Score Analysis

PEGU = **P**rice momentum (Darvas) + **E**cosystem / financial health (Piotroski) + **G**rowth quality (Coffee Can) + **U**niverse validation

## India (NSE + BSE) — 4,805 stocks scored

| Grade | Count | Description |
|---|---|---|
| B+ | 8 | Breakout + Piotroski ≥ 7 + Coffee Can PASS |
| B | 21 | Breakout + moderate fundamentals |
| C | 228 | Partial signals |
| D / F | 4,548 | Weak or no signals |

> [`data/india_pegu_scored.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/india_pegu_scored.csv)

## Germany (Eurex) — 1,497 stocks scored

| Grade | Count | Description |
|---|---|---|
| A+ | 3 | Full derivative suite (4/4) |
| A | 8 | Near-full suite, deep coverage |
| B+ | 26 | 3/4 types, strong institutional tracking |
| B | 11 | 2/4 types, moderate coverage |
| C+ / C | 1,449 | Limited derivatives (futures or dividend only) |

> [`data/german_pegu_scored.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/german_pegu_scored.csv)

---

# Data & Scripts

| File | Description |
|---|---|
| [`data/validated_universe_flat.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/validated_universe_flat.csv) | 60,971 validated global tickers |
| [`data/india_pegu_scored.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/india_pegu_scored.csv) | India PEGU scores (NSE+BSE) |
| [`data/german_pegu_scored.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/german_pegu_scored.csv) | German market PEGU scores (Eurex) |
| [`data/eurex_pegu_all_europe.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/eurex_pegu_all_europe.csv) | Pan-European PEGU scores (1,925 stocks) |
| [`data/eurex_products.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/eurex_products.csv) | 3,022 Eurex products (live, Jul 2026) |
| [`data/eurex_trading_hours.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/eurex_trading_hours.csv) | Trading session times (2,019 products) |
| [`data/eurex_holidays.csv`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/data/eurex_holidays.csv) | Exchange holiday calendar (2026–2028) |
| [`german_market/eurex_graphql.py`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/german_market/eurex_graphql.py) | Eurex GraphQL API client (v2.0.0) |
| [`german_market/german_pegu_score.py`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/german_market/german_pegu_score.py) | German PEGU scoring engine |
| [`validate_universe_fd.py`](https://github.com/herrrickshaw/BMS_analysis_battery/blob/claude/nse-bse-pegu-scoring-k7vu9/validate_universe_fd.py) | Universe validation via FinanceDatabase |
