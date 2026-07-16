# Decision Register — Price Prediction, Circuit-Breaker Validation & PEAD/Spillover

Every non-obvious design choice in `regime_price_model*.py`, `build_mailer.py`'s
circuit-breaker sanity bounds, `backtest_circuit_breaker_darvas.py`, and the
`pead_sector_spillover*.py` / `cross_sectional_momentum.py` / `liquidity.py`
event-study work is recorded here with the literature source that motivated
it. The goal is traceability: a reviewer should be able to ask "why this
number / why this architecture" and find the answer is a cited finding, not
an arbitrary choice.

Full source PDFs for the circuit-breaker/signal-processing register (`[FP16]`
through `[EURONEXT-TS]`) are in `~/Downloads/`. The PEAD & Sector-Spillover
register below cites classic accounting/finance/statistics papers referenced
in code docstrings but not locally archived as PDFs — citations are complete
and independently verifiable, just not paired with a local file. Citation
keys below match the docstring citations already in the code (`[FP16]`,
`[ICCT15]`, `[BB68]`, etc.).

## Source register

| Key | Full citation | Type | Role |
|---|---|---|---|
| `[FP16]` | Feng, Y. & Palomar, D.P. *A Signal Processing Perspective on Financial Engineering*. Foundations and Trends in Signal Processing, 9(1-2), 1–231 (2016). | Peer-reviewed monograph | Primary methodological source — return/volatility modeling, VECM mean-reversion |
| `[ICCT15]` | Iyer, S., Kamdar, N.R. & Soparkar, B. *Stock Market Prediction using Digital Signal Processing Models*. Int'l Conf. on Computer Technology, IJCA (2015). | Peer-reviewed conference paper | Closed-form (Prony/normal-equation) fitting beats gradient descent; train/test discipline |
| `[IJCSE20]` | Tebepah, I.R. *Digital Signal Processing for Predicting Stock Prices Using IBM Cloud Watson Studio*. SSRG-IJCSE 7(1) (2020). | Peer-reviewed survey | Directional/regime classification framing |
| `[DSP22]` | Idahtonye, T. & Luckyn, B.J. *Digital Signal Processing For Predicting Exchange Markets*. J. Software Engineering and Simulation 8(9) (2022). | Peer-reviewed (weak methodology, small n) | Naive MA-crossover baseline only |
| `[JSTSP-CFP]` | Akansu, A.N. et al. *Call for Papers: Special Issue on Financial Signal Processing and Machine Learning for Electronic Trading*. IEEE J. Selected Topics in Signal Processing (2015). | Editorial call for papers, IEEE Signal Processing Society | Establishes "financial signal processing" as a recognized cross-disciplinary field — not an ad hoc mashup of unrelated techniques |
| `[KHATOON25]` | Khatoon, W. *Market-Wide Circuit Breakers: A Critical Analysis of Their Impact on Stock Market Stability in India*. Int'l J. of Advances in Business and Management Research 2(3), 49–62 (2025). DOI: 10.62674/ijabmr.2025.v2i03.006 | Peer-reviewed original article | India MWCB structure, magnet effect, downside-panic asymmetry |
| `[NSE-PB]` | NSE India. *Price Bands*. nseindia.com/static/products-services/equity-market-price-bands (accessed 2026-07-16). | Primary/official exchange source | India stock-wise static price bands (2/5/10/20%) + F&O dynamic band |
| `[ZERODHA-FO]` | Zerodha. *Explainer on new price band rules for stocks trading in the F&O segment*. zerodha.com/z-connect (accessed 2026-07-16). | Broker explainer, corroborating | F&O dynamic band = 10% base, expands with 15-min cooling-off |
| `[KRX-GUIDE]` | Korea Exchange. *Guide to Trading in the Korean Stock Market*. global.krx.co.kr (accessed 2026-07-16). | Primary/official exchange source | KRX flat ±30% daily price limit, since 2015 |
| `[NASDAQ-CB]` | Nasdaq Trader. *Circuit Breaker*. nasdaqtrader.com/trader.aspx?id=CircuitBreaker (accessed 2026-07-16). | Primary/official market-data source | US S&P 500 Market-Wide Circuit Breaker (MWCB): 7%/13%/20% |
| `[LULD-FAQ]` | Nasdaq. *Limit Up-Limit Down FAQ*. nasdaqtrader.com (accessed 2026-07-16). | Primary/official | US LULD is a re-centering PAUSE band (5/10/20%), not a daily cap |
| `[JPX-DPL]` | Japan Exchange Group. *Daily Price Limits*. jpx.co.jp/english/equities/trading/domestic/06.html (accessed 2026-07-16). | Primary/official exchange source | TSE absolute-yen price-limit table (not a flat %) |
| `[EHOUSING-NKY]` | e-housing.jp. *Nikkei Future Japan Exchange* (accessed 2026-07-16). | Secondary explainer, non-academic — used only to corroborate `[JPX-DPL]`'s existence and describe the SEPARATE Nikkei/TOPIX futures Static Circuit Breaker (8%→12%) | Confirms yen-limit structure for equities; explicitly NOT used as the source for the equity bound itself (see D-05) |
| `[EURONEXT-TS]` | Euronext. *Trading Safeguards on the Euronext Markets*. euronext.com (accessed 2026-07-16). | Primary/official | Static collar ±8% blue-chip / ±10% other — not used in current code (no EU Change% yet), recorded for future extension |

---

## Decisions

### D-01 — Model log-returns, not prices
**Decision**: every predictive model in `regime_price_model.py` targets `r_fwd` (next-day log-return), never the raw price level.
**Literature basis**: `[FP16]` §2.1: log-prices are non-stationary (a stock's log-price trends upward indefinitely), while log-returns are approximately stationary and additive over time — the property required for any of the closed-form estimators used downstream (§2.1.2, eq. 2.5–2.6).
**Where**: `regime_price_model.py:_extract_features()`, the `logret` array.

### D-02 — Two regime-conditional sub-models (mean-reversion vs momentum), not one pooled model
**Decision**: consolidation (`IN_BOX`) days are modeled as reverting toward the box midpoint; breakout/breakdown days are modeled with short-lag momentum. The two are fit and evaluated separately, never pooled.
**Literature basis**:
- Mean-reversion form directly mirrors `[FP16]` Ch.10's VECM/statistical-arbitrage spread — a stationary "spread" `z_t` that reverts to zero, with buy/sell thresholds `±s0` (§10.1.3, Fig. 10.5–10.6). Here the spread is distance from the Darvas box midpoint instead of a cross-asset pair spread.
- Momentum form is `[FP16]` eq. (2.34), a VAR(p) on the conditional mean.
- `[KHATOON25]` p.52 independently supports keeping breakout and breakdown as SEPARATE regimes rather than symmetric: its event-study literature review reports "investors tend to panic more when the markets show intense movements in the downward direction than in the upward direction" — an empirically-grounded asymmetry that would be lost if BREAKOUT and BREAKDOWN shared one coefficient.
**Where**: `regime_price_model.py:fit_and_evaluate()` (`theta_a` for consolidation, `theta_b` for momentum), and the separate `momentum_breakout` / `momentum_breakdown` test-set scores.

### D-03 — Closed-form OLS (normal equations), not gradient descent
**Decision**: both sub-models are fit via `np.linalg.lstsq` (equivalent to `θ = (XᵀX)⁻¹Xᵀy`), never an iterative gradient-descent loop.
**Literature basis**: `[ICCT15]` §5 directly compared the two on real NASDAQ data (MSFT, 2010–2015): gradient-descent linear regression got worse MSE than "Prony's Normal Equation" (the same closed-form least-squares solution) specifically for TIME-SERIES continuation tasks — the paper's own conclusion (p.38): "the analysis of time series input using Normal Equation method is more accurate," and cites the added benefit that closed-form fitting needs no learning-rate tuning.
**Where**: `regime_price_model.py:_ols()`, `_ols_with_inference()`.

### D-04 — Chronological (not random) train/test split, honest reporting of a null result
**Decision**: train ≤ 2023-12-31, test ≥ 2024-01-01, no shuffling; results reported even when they show no edge.
**Literature basis**: `[ICCT15]` used the same discipline (2/3 train, 1/3 test, in time order) and explicitly cites Goyal & Welch (2006) — "stock returns are hardly predictable in the out-of-sample context" — as the reason the reported numbers must be taken at face value rather than assumed profitable. The negative result obtained on India's full 400-symbol panel (and confirmed again across all four markets' full universes, see `regime_price_model_cross_market.py`) is consistent with, not contradictory to, this cited finding.
**Where**: `regime_price_model.py:TRAIN_END`, `TEST_START`.

### D-05 — Per-market circuit-breaker bounds are NOT one constant
**Decision**: `CIRCUIT_BOUND_PCT = {"IN": 20.0, "KR": 30.0, "US": 100.0, "JP": 50.0}` — four different numbers, two of them exact rules and two of them documented heuristics, rather than a single flat percentage applied everywhere (the mistake corrected earlier this session — see D-05a).
**Literature basis, per market**:
- **India, 20%** — `[NSE-PB]`: static price bands of 2/5/10/20% assigned per non-F&O stock, plus a flat 20% band on auction-market scrips, debentures, and preference shares; `[ZERODHA-FO]` corroborates the ~200 F&O-eligible names instead use a 10% DYNAMIC band that expands with a 15-minute cooling-off, so 20% remains the correct outer ceiling across all India equity types (F&O names are actually tighter, never wider). **Important distinction** (see D-05a): this is the STOCK-WISE price limit, a different mechanism from India's MARKET-WIDE circuit breaker.
- **Korea, 30%** — `[KRX-GUIDE]`: a flat, symmetric daily price limit on KOSPI/KOSDAQ stocks, ETFs and ETNs, tightened from ±15% to ±30% in 2015. This is the one EXACT (non-heuristic) bound in the table — no per-stock variation exists in KRX's rule the way it does in India or Japan.
- **US, 100%** — `[LULD-FAQ]`, `[NASDAQ-CB]`: no daily price CAP exists for individual US equities. LULD only PAUSES trading inside a re-centering 5/10/20% band around a rolling 5-minute reference price (`[LULD-FAQ]`); genuine >50% single-session moves are legitimately possible (biotech catalysts, low-float squeezes) and must not be clamped away. 100% is retained explicitly as a data-sanity heuristic, not a regulatory bound — documented as such in code so a future reader doesn't mistake it for a real US rule.
- **Japan, 50%** — `[JPX-DPL]`, corroborated by `[EHOUSING-NKY]`: TSE's Daily Price Limit is an ABSOLUTE-YEN table keyed to the previous close (e.g. ¥1,000 close → ¥700–1,300 band, ≈±30%), not one flat percentage — narrower in % terms at higher price tiers, wider for penny-priced stocks. Because the full table could not be scraped from `[JPX-DPL]` (blocked automated fetch) and `[EHOUSING-NKY]` describes a DIFFERENT instrument (Nikkei/TOPIX index FUTURES' 8%→12% Static Circuit Breaker, not individual TSE equities), 50% is used as a conservative heuristic covering the widest realistic yen-tier band — explicitly NOT claimed as an exact rule, unlike India and Korea.
**Where**: `regime_price_model.py:CIRCUIT_BOUND_PCT`, `build_mailer.py:_CIRCUIT_BREAKER_PCT` (India/US only, since only those two markets currently have a Change% column in the mailer).

### D-05a — Market-wide (index-level) circuit breakers are a DIFFERENT mechanism, not conflated with the per-stock bound
**Decision**: `CIRCUIT_BOUND_PCT` values are per-STOCK bounds only. India's and the US's separate index-level Market-Wide Circuit Breaker (MWCB) thresholds are recorded here for completeness but are NOT used as a per-stock prediction clamp.
**Literature basis**: `[KHATOON25]` p.49–50 (Fig. 1–2) gives India's exact SEBI MWCB structure — Nifty/Sensex index decline of 10% (before 1pm: 45-min halt; 1–2:30pm: 15-min halt; after 2:30pm: no halt), 15% (before 1pm: 1h45m halt; 1–2pm: 45-min halt; after 2pm: remainder-of-day), 20% (any time: remainder-of-day) — explicitly an INDEX-level mechanism, distinct from the per-stock 2/5/10/20% price bands in `[NSE-PB]` (the paper's own taxonomy, p.49: "price limits i.e. stock wise trading halts" vs "firm-specific trading halts" vs "market wide circuit breakers" are three DIFFERENT things). `[NASDAQ-CB]` gives the US analogue: S&P 500 decline of 7%/13%/20% (Level 1/2/3), 15-minute halts for Level 1–2, remainder-of-day for Level 3 — again index-level, and structurally separate from LULD (`[LULD-FAQ]`), which operates per-stock.
**Why this matters**: it would be a real modeling error to apply India's 20% per-stock static-band bound and its coincidentally-identical 20% market-wide Level-3 threshold as if they were the same rule — they trigger on different underlying quantities (one stock's price vs. the whole index) and this register exists partly to make sure that conflation doesn't happen silently in a future edit.
**Where**: documented here only; not yet wired into any index-level sanity check (no index-return prediction exists in the current codebase to apply it to).

### D-06 — Predictions are HARD-CLAMPED to the circuit bound, not just flagged
**Decision**: `_predict()` in `regime_price_model.py` clips every point prediction to `[-bound, +bound]` in log-return space before it is ever scored or reported — not a post-hoc warning, an enforced constraint.
**Literature basis**: `[KHATOON25]` p.51 reports the "magnet effect" (citing Wong, Kong & Li 2020, *Pacific-Basin Finance Journal*): as price approaches a circuit breaker or price limit, volatility rises drastically and the probability of actually triggering the breaker increases — in one measured proximity band, "the magnet effect of price ceiling increased sixfold when the market index approached 3% of the circuit-breaker threshold." This is direct empirical evidence that price behavior gets LESS well-behaved, not more, near the boundary — a linear model extrapolating on an outlier input feature is therefore MORE, not less, likely to emit a physically-impossible prediction in exactly this regime, which is precisely why the clamp is enforced unconditionally rather than trusted to bind rarely by construction. This also directly extends the same discipline already applied earlier this session to `build_mailer.py`'s Change% sanity bound (the ARIHANT +2188.9%/XAIR +1273.8% bad-data incidents that motivated `_CIRCUIT_BREAKER_PCT` in the first place).
**Where**: `regime_price_model.py:_predict()`, `_circuit_bound_logret()`.

### D-07 — GARCH(1,1) for volatility, not a constant/flat sigma
**Decision**: `garch_volatility()` fits GARCH(1,1) per symbol via the `arch` package rather than using a flat historical standard deviation.
**Literature basis**: `[FP16]` eq. (2.58)–(2.59) and Example 2.2/2.3 (Fig. 2.2–2.3) show empirically that real equity returns exhibit "volatility clustering" (high volatility is more likely followed by high volatility) which a constant-variance model cannot capture, and that GARCH(1,1) captures this persistence with far fewer parameters than a high-order ARCH model (3 parameters vs. 10 for a comparably persistent ARCH(9), Example 2.3, p.37–38). `[KHATOON25]`'s magnet-effect finding (D-06) is additional, market-structure-specific motivation: volatility clustering is expected to be STRONGEST exactly near a circuit-breaker boundary, which is exactly where GARCH's conditional (not unconditional) sigma matters most for sizing a confidence band.
**Where**: `regime_price_model.py:garch_volatility()`.

### D-08 — Directional accuracy reported alongside RMSE, not RMSE alone
**Decision**: every evaluation reports `dir_acc` (sign-match rate) as a co-equal metric to RMSE-skill, never RMSE in isolation.
**Literature basis**: `[IJCSE20]`'s literature review (§II.A) surveys multiple studies (Basak et al. 2019, Wanjawa & Muchemi 2014) that frame the prediction task as DIRECTION classification rather than exact price regression, and concludes a single algorithm's raw accuracy on price level is often less informative than whether it gets the sign right — directly motivating the directional-accuracy metric used throughout `regime_price_model.py`'s `_score()`.
**Where**: `regime_price_model.py:_score()`, `regime_price_model_cross_market.py:_score_test()`.

### D-09 — The whole "signal processing for markets" framing is not ad hoc
**Decision**: the codebase treats return prediction, volatility modeling, and circuit-breaker bounding as a coherent signal-processing problem (stationarity, filtering, closed-form estimation) rather than an assortment of unrelated heuristics.
**Literature basis**: `[JSTSP-CFP]` is the IEEE Signal Processing Society's own call for papers establishing "Financial Signal Processing and Machine Learning for Electronic Trading" as a recognized special-issue topic area, explicitly listing "covariance modeling," "market microstructure modeling," and "signal processing algorithms for electronic trading" as in-scope — i.e., an editorial board of five named guest editors (Akansu/NJIT, Jay/QAMLab, Malioutov/IBM Research, Mandic/Imperial College London, Palomar/HKUST — the same Palomar as `[FP16]`) considers this a legitimate cross-disciplinary research area, not a novel or unusual combination invented for this task.
**Where**: this register; `regime_price_model.py`'s module docstring.

---

---

## Source register — PEAD & Sector-Spillover

| Key | Full citation | Type | Role |
|---|---|---|---|
| `[BB68]` | Ball, R. & Brown, P. *An Empirical Evaluation of Accounting Income Numbers*. Journal of Accounting Research, 6(2), 159–178 (1968). | Peer-reviewed, foundational | Original discovery of post-earnings-announcement drift |
| `[BT89]` | Bernard, V.L. & Thomas, J.K. *Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?* Journal of Accounting Research, 27, 1–36 (1989). | Peer-reviewed | Drift persists for weeks post-announcement; not explained by risk |
| `[BT90]` | Bernard, V.L. & Thomas, J.K. *Evidence That Stock Prices Do Not Fully Reflect the Implications of Current Earnings for Future Earnings*. Journal of Accounting and Economics, 13(4), 305–340 (1990). | Peer-reviewed | Motivates the pos-minus-neg CAR spread (growing with horizon) as the diagnostic for genuine drift |
| `[F81]` | Foster, G. *Intra-Industry Information Transfers Associated with Earnings Releases*. Journal of Accounting and Economics, 3(3), 201–232 (1981). | Peer-reviewed, foundational | One firm's earnings news moves same-industry peers |
| `[TZ08]` | Thomas, J. & Zhang, F. *Overreaction to Intra-Industry Information Transfers?* Journal of Accounting Research, 46(4), 909–940 (2008). | Peer-reviewed | Motivates testing spillover per-candidate across MULTIPLE events, not a one-shot correlation |
| `[FOS84]` | Foster, G., Olsen, C. & Shevlin, T. *Earnings Releases, Anomalies, and the Behavior of Security Returns*. The Accounting Review, 59(4), 574–603 (1984). | Peer-reviewed | Seasonal-random-walk surprise proxy when no analyst consensus exists |
| `[BW80/85]` | Brown, S.J. & Warner, J.B. *Measuring Security Price Performance*. J. Financial Economics, 8(3), 205–258 (1980); *Using Daily Stock Returns: The Case of Event Studies*. J. Financial Economics, 14(1), 3–31 (1985). | Peer-reviewed | Simple mean/market-adjusted abnormal-return models perform comparably to complex ones at event-study horizons |
| `[MG99]` | Moskowitz, T.J. & Grinblatt, M. *Do Industries Explain Momentum?* Journal of Finance, 54(4), 1249–1290 (1999). | Peer-reviewed | Sector/industry-neutral cross-sectional momentum |
| `[A02]` | Amihud, Y. *Illiquidity and Stock Returns: Cross-Section and Time-Series Effects*. Journal of Financial Markets, 5(1), 31–56 (2002). | Peer-reviewed | ILLIQ price-impact measure for liquidity tiering |
| `[BH95]` | Benjamini, Y. & Hochberg, Y. *Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing*. Journal of the Royal Statistical Society: Series B, 57(1), 289–300 (1995). | Peer-reviewed, foundational (statistics) | Multiple-testing correction across all spillover candidates tested, not just the ones that look interesting |

## Decisions — PEAD & Sector-Spillover

### D-10 — PEAD measured as sector-adjusted CAR conditioned on surprise sign; the pos-minus-neg SPREAD, not raw CAR, is the diagnostic
**Decision**: `pead_summary` reports CAR separately for positive- and negative-surprise events at each horizon, and treats `{horizon}_pos_minus_neg_spread_pct` as the load-bearing number — a spread that stays positive and grows with horizon is evidence of real drift; similar CARs for both signs indicates a generic positive-drift artifact unrelated to the surprise itself.
**Literature basis**: `[BB68]` established that returns keep drifting in the direction of the surprise after the announcement. `[BT89]`/`[BT90]` showed this persists for weeks and isn't a risk premium — `[BT90]` in particular is why the spread (not the level) is the right test: a market that fully reacted to earnings news would show a flat spread near zero, not a growing one.
**Where**: `pead_sector_spillover.py:202-223`, unchanged through v2/v3/v4.

### D-11 — Sector-spillover ("leader") status requires a same-direction hit-rate across MULTIPLE separate events, not a single-event correlation
**Decision**: a candidate ticker needs ≥3 of its own earnings events (`MIN_EVENTS_FOR_LEADER`) before it's even tested; "leader" status is a binomial test on the hit-rate across all of them, not a one-quarter coincidence.
**Literature basis**: `[F81]` is the original finding that one firm's earnings release moves same-industry peers. `[TZ08]` specifically frames this as something that should be measured across a firm's REPEATED announcement history, not inferred from one event — motivating `MIN_EVENTS_FOR_LEADER` and the per-ticker binomial test over `n` events rather than flagging any single large peer reaction.
**Where**: `pead_sector_spillover.py:225-260` (`spillover_rows` aggregation, `MIN_EVENTS_FOR_LEADER = 3`).

### D-12 — YoY net-income growth as the surprise proxy when no analyst consensus exists (v1 only)
**Decision**: `load_events()` (v1's default events loader) computes `surprise = (net_income − prior_year_net_income) / |prior_year_net_income|` rather than leaving surprise undefined when no I/B/E/S-style consensus estimate is available.
**Literature basis**: `[FOS84]` is the original justification for a "seasonal random walk" earnings-expectation proxy (this quarter's number is expected to equal the same quarter a year ago) when consensus data doesn't exist — exactly the situation this repo is in, since no analyst-estimate source was ever collected.
**Where**: `pead_sector_spillover.py:load_events()`. Superseded for numeric events by real consensus-based `surprise_pct` from yahooquery/yfinance starting in v2, but v1 remains runnable and is still the fallback shape other loaders match.

### D-13 — Abnormal return = leave-one-out equal-weight sector benchmark, not a full CAPM/Fama-French residual
**Decision**: `_sector_leave_one_out_returns()` computes each event's abnormal return as the stock's own return minus the equal-weighted return of every OTHER stock in its sector that day — no beta estimation, no factor model.
**Literature basis**: `[BW80/85]` is the standard event-study methodology citation showing that simple mean/market-adjusted abnormal-return models perform comparably to more complex risk-adjusted models at the short event windows used here (1/2/3-month CARs), making a full factor model unnecessary complexity for this task.
**Where**: `pead_sector_spillover.py:_sector_leave_one_out_returns()`, reused by every PEAD/spillover computation and by `cross_sectional_momentum.py`.

### D-14 — Cross-sectional momentum tested peer-relative (vs. sector peers), not each stock vs. its own past
**Decision**: `cross_sectional_momentum.py` ranks stocks against their OWN sector's other members at each horizon (3d/1wk/2wk/1mo), rather than comparing a stock's recent return to its own historical average (time-series momentum).
**Literature basis**: `[MG99]` is the origin of industry/sector-neutral momentum — showing that a meaningful share of individual-stock momentum is actually explained by INDUSTRY momentum, which motivates testing momentum peer-relative within a sector rather than stock-vs-self.
**Where**: `cross_sectional_momentum.py` (module docstring cites `[MG99]` directly).

### D-15 — Amihud ILLIQ for liquidity tiering, not raw market cap or turnover alone
**Decision**: `liquidity.py:amihud_illiq()` computes price-impact-per-dollar-traded and uses it (alongside turnover) to gate/tier stocks by liquidity, rather than relying on market cap as a liquidity proxy.
**Literature basis**: `[A02]` is the original ILLIQ measure — |return| / dollar volume as a price-impact estimate — and its own finding that illiquidity commands a return premium is the reason liquidity tiering matters at all for this repo's factor work, not just a data-cleaning step.
**Where**: `liquidity.py:amihud_illiq()`, `_scan_floor()`, `scan_gate()`.

### D-16 — Benjamini-Hochberg FDR correction (q=0.10) across ALL candidates tested, not raw p<0.05 on the ones that look interesting
**Decision**: every "good performer moves its peers" leader search ranks candidates by p-value and applies the standard BH step-up procedure across the FULL tested set (`n_leader_candidates_tested`, typically 140–464 depending on market) before calling anything significant — never just eyeballing the smallest p-values.
**Literature basis**: `[BH95]` is the canonical multiple-testing correction — testing hundreds of tickers at face-value p<0.05 would produce dozens of false positives from chance alone; BH-FDR bounds the expected false-discovery proportion among rejected hypotheses instead.
**Where**: `pead_sector_spillover.py:229-260`, unchanged through v2/v3/v4. Directly responsible for narrowing the US "good performer" list from 8 nominally-significant tickers down to the 1-3 that actually survive correction (MCHP always; ANET/WDAY inconsistently, see D-17).

### D-17 — Full-sample significance is validated with an explicit train/test split and confound checks before being trusted, not accepted at face value
**Decision**: `pead_walkforward_validate.py` re-runs the unchanged statistical core on chronologically split TRAIN/TEST folds, and separately checks candidates against (a) their own negative-surprise-day behavior, (b) the sector's unconditional base rate, and (c) same-sector peers with identical event counts — before treating any full-sample FDR-significant result as real.
**Literature basis**: this extends D-04's chronological train/test discipline (`[ICCT15]`, Goyal & Welch's out-of-sample skepticism) into the event-study setting; the three confound checks are this session's own diagnostic design in response to a specific observed risk (MCHP/ANET/WDAY's surprise sign was 26-28/28 positive, so a "same-direction hit rate" could otherwise just be re-measuring bull-market sector drift) rather than a technique drawn from a specific paper.
**Where**: `pead_walkforward_validate.py`. Result: MCHP passed every check; ANET/WDAY passed the confound checks but showed weaker/inconsistent significance across the temporal split, downgraded from "confirmed" to "watch" accordingly.

### D-18 — price_change_* sanity bound reuses D-05's per-market circuit-breaker regime, not a new invented threshold
**Decision**: `earnings_price_dataset.py:_price_change_bound_pct()` nulls out any computed 1d/5d/21d price change beyond a bound derived from the SAME `CIRCUIT_BOUND_PCT` dict as D-05/D-06 (worst-case N-consecutive-limit-days compounding for the multi-day windows), rather than a flat or market-blind cutoff.
**Literature basis**: no new source — a direct extension of D-05's per-market bounds (`[NSE-PB]`, `[KRX-GUIDE]`, `[LULD-FAQ]`, `[JPX-DPL]`) and D-06's magnet-effect-motivated hard-clamping (`[KHATOON25]`) to a second dataset, kept in the same file family (`regime_price_model.CIRCUIT_BOUND_PCT` imported directly, not redefined) so the two never silently drift apart.
**Where**: `earnings_price_dataset.py:_price_change_bound_pct()`, `compute_price_changes()`. Caught a real -69.2% one-day India move (impossible under `[NSE-PB]`'s 20% limit) and a repeated 230.3% Korea value (impossible under `[KRX-GUIDE]`'s 30% limit) — both data errors, not real trading.

---

## Known gaps (explicitly not yet addressed, for a future extension)

- **Europe** has a documented static-collar rule (`[EURONEXT-TS]`: ±8% blue-chip / ±10% other) but no `Change%` column exists yet for Europe in `build_mailer.py`, so no bound has been wired in. Xetra (`[XETRA-PM]`, not yet fetched in full) uses volatility-interruption auctions instead of a fixed cap, so a single EU-wide number would need the same per-exchange care as Japan's yen-table, not a flat percentage.
- **Japan's exact per-tier yen table** (`[JPX-DPL]`) could not be scraped (403 on automated fetch); the current 50% bound is a documented heuristic, not the precise rule. Manually transcribing the table from the JPX page would let D-05's Japan bound move from "heuristic" to "exact," matching India and Korea.
- **Post-breach dynamics** (`[KHATOON25]` p.53: circuit-breaker effects on volatility/returns persist "up to 10 days in most cases and up to 20 days in some cases") are not modeled — the current regime model only predicts one day ahead and treats every day independently once past a circuit event.
