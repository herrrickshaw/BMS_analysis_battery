# PIT event studies (India) — generated 2026-07-23 06:22

The XBRL × corporate-actions × bhavcopy join. All returns are
cumulative ABNORMAL log returns (symbol − daily market median) on
split/bonus-ADJUSTED prices. Event timing is the NSE broadcast
timestamp; after-15:30 broadcasts anchor to the next trading day —
fully point-in-time, no period-end dating anywhere.

## 1. PEAD sorted on announcement-window [0,+1] abnormal return

64,263 filing-dated events (of 66,229 in the index; the
rest fall outside the 2016+ adjusted panel or lack price coverage).
Quintiles are WITHIN calendar quarter (cross-sectional).

| quintile | n | ann ret (med) | CAR +2..+21 | CAR +2..+63 | hit(63d) |
|---|---|---|---|---|---|
| Q1 | 11,287 | -7.48% | +4.75% | +13.52% | 73% |
| Q2 | 11,268 | -2.61% | +4.31% | +12.80% | 78% |
| Q3 | 11,269 | -0.52% | +4.51% | +13.55% | 80% |
| Q4 | 11,271 | +1.48% | +4.66% | +14.24% | 80% |
| Q5 | 11,275 | +6.74% | +5.34% | +14.61% | 74% |

Reading: classic PEAD predicts Q5 (best announcement reaction)
drifts UP and Q1 drifts DOWN. Q5−Q1 CAR63 spread = +1.09%.

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

## Caveats (encode before citing)
- Median-market abnormal returns, no beta adjustment — factor-model
  CARs are the upgrade path.
- results_index 2025 is thin (3,960 rows vs ~11k/yr) — collection
  gap, not a market fact; drift estimates for 2025 cohorts are
  under-sampled.
- Announcement-return sorting conditions on day-0/+1 price action
  (tradeable from day +2); it is NOT a fundamentals surprise.
- No FDR pass yet: treat every spread here as PROVISIONAL until
  multiple_testing.py includes these families.
