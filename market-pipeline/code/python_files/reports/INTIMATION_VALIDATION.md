# Intimation-drift validation — 2026-07-23 12:26

Matched benchmark: each event vs the MEDIAN CAR of same-month,
same-turnover-decile symbols over the identical calendar window
(median 186 controls/event). Inference:
calendar-quarter clustered t (events overlap in time).
FDR family: 18 hypotheses = 6 event-study tests
+ the factor-combo grid from MULTIPLE_TESTING.md. BH q=0.10/0.05.

| hypothesis | n | qtrs | mean effect | median | t | p | q=.10 | q=.05 |
|---|---|---|---|---|---|---|---|---|
| intimation drift (split) vs matched controls | 258 | 40 | +8.47% | +7.05% | +5.82 | 0.0000 | ✅ | ✅ |
| intimation drift (bonus) vs matched controls | 295 | 41 | +5.13% | +3.54% | +2.26 | 0.0293 | — | — |
| grid: US not_distress (control) | — | — | — | — | — | 0.0388 | — | — |
| grid: US low_asset_growth (control) | — | — | — | — | — | 0.0399 | — | — |
| grid: US roce_plus + debt_reduction | — | — | — | — | — | 0.1547 | — | — |
| PEAD ann-ret Q5-Q1 CAR63 | 73539 | 42 | +0.88% | +1.01% | +1.35 | 0.1846 | — | — |
| grid: US piotroski + debt_reduction | — | — | — | — | — | 0.2898 | — | — |
| grid: INDIA piotroski + debt_reduction | — | — | — | — | — | 0.3287 | — | — |
| grid: INDIA debt_reduction | — | — | — | — | — | 0.3300 | — | — |
| grid: INDIA roce_plus | — | — | — | — | — | 0.4202 | — | — |
| grid: INDIA piotroski | — | — | — | — | — | 0.4260 | — | — |
| grid: US roce_plus | — | — | — | — | — | 0.4332 | — | — |
| post-ex drift 0..+20 (bonus) | 379 | 41 | -0.19% | -1.11% | -0.77 | 0.4438 | — | — |
| PEAD surprise T3-T1 CAR63 (naive t) | 83 | — | -6.14% | +2.44% | -0.44 | 0.6613 | — | — |
| grid: US debt_reduction | — | — | — | — | — | 0.8768 | — | — |
| grid: US piotroski | — | — | — | — | — | 0.8822 | — | — |
| post-ex drift 0..+20 (split) | 343 | 43 | -0.09% | -1.27% | -0.15 | 0.8851 | — | — |
| grid: US piotroski + roce_plus | — | — | — | — | — | 0.8932 | — | — |

Survivors at q=0.10: 1 / 18; at q=0.05: 1.

claims.yaml policy: only q=0.10 survivors are citable as validated.
