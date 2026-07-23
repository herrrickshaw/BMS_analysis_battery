# PIT event studies (India) — generated 2026-07-23 07:05

The XBRL × corporate-actions × bhavcopy join. All returns are
cumulative ABNORMAL log returns (symbol − daily market median) on
split/bonus-ADJUSTED prices. Event timing is the NSE broadcast
timestamp; after-15:30 broadcasts anchor to the next trading day —
fully point-in-time, no period-end dating anywhere.

## 1. PEAD sorted on announcement-window [0,+1] abnormal return

76,435 anchored filing-dated events (deduped index universe:
78,799; the rest fall outside the 2016+ adjusted panel
or lack price coverage).
Quintiles are WITHIN calendar quarter (cross-sectional).

| quintile | n | ann ret (med) | CAR +2..+21 | CAR +2..+63 | hit(63d) |
|---|---|---|---|---|---|
| Q1 | 13,383 | -6.97% | +4.28% | +11.53% | 69% |
| Q2 | 13,362 | -2.34% | +3.88% | +10.98% | 74% |
| Q3 | 13,358 | -0.42% | +3.96% | +11.67% | 75% |
| Q4 | 13,365 | +1.41% | +4.06% | +12.23% | 75% |
| Q5 | 13,369 | +6.18% | +4.64% | +12.39% | 70% |

Reading: classic PEAD predicts Q5 (best announcement reaction)
drifts UP and Q1 drifts DOWN. Q5−Q1 CAR63 spread = +0.86%.

## 2. PEAD sorted on PAT YoY surprise (parsed-XBRL subset)

83 events with a same-file year-ago quarter.

| tercile | n | surprise (med) | CAR +2..+21 | CAR +2..+63 | hit(63d) |
|---|---|---|---|---|---|
| T1 | 28 | -54% | +20.85% | +25.85% | 71% |
| T2 | 27 | +29% | +0.46% | +5.74% | 70% |
| T3 | 28 | +133% | +5.32% | +19.70% | 86% |

Small sample — directional read only; grows as the XML
parse queue drains (2,194 of 110,942 filings parsed).

## 3. Post-split / post-bonus event study (ex-date anchored)

| kind | n | CAR −20..−1 | CAR 0..+20 | CAR +21..+60 | hit(0..+20) |
|---|---|---|---|---|---|
| bonus | 379 | +9.85% | -0.19% | +5.09% | 47% |
| split | 343 | +14.38% | -0.09% | +4.73% | 47% |

## 3b. Intimation-anchored: was the pre-ex run-up tradeable?

Anchor = board-meeting INTIMATION broadcast (bm_timestamp — the
first public signal a bonus/split is being considered; NSE's
caBroadcastDate field is null in every corp-actions row).
`react` = intimation day 0..+1 (not tradeable in advance);
`drift` = day +2 .. ex−1 (fully tradeable window).

| kind | n | gap (td, med) | CAR react [0,+1] | CAR drift [+2,ex−1] | hit(drift) |
|---|---|---|---|---|---|
| bonus | 295 | 35 | +5.64% | +10.37% | 75% |
| split | 258 | 50 | +5.70% | +16.48% | 83% |

Sum react+drift vs Study 3's pre-ex run-up tells how much of the
anticipation was announced-then-earned vs already priced before
any public intimation.

## Caveats (encode before citing)
- 🔴 LEVEL BIAS: every quintile carries ~+13%/63d abnormal CAR — the
  filing universe (2,495 real, alive companies) systematically beats
  the all-panel median benchmark (microcap drag), and the inner-join
  window requires 63 subsequent bars (within-window survivorship).
  ONLY CROSS-SECTIONAL SPREADS (Q5−Q1, T3−T1, pre-vs-post) are
  interpretable; never cite a level.
- Median-market abnormal returns, no beta adjustment — factor-model
  CARs are the upgrade path.
- 2025-26 index coverage RESTORED 2026-07-23 via the integrated-
  filing API (NSE silently migrated post-2024 results there); the
  legacy-API-only era of this index under-sampled 2025 cohorts.
- Study 3b hit rates ride the same universe-level bias — compare
  its 75-83% drift hits against the ~70-75% baseline hit of the
  filing universe, not against 50%.
- Announcement-return sorting conditions on day-0/+1 price action
  (tradeable from day +2); it is NOT a fundamentals surprise.
- No FDR pass yet: treat every spread here as PROVISIONAL until
  multiple_testing.py includes these families.
