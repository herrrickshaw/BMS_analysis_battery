# Multiple-testing control — generated 2026-07-22 18:22

Grid: 12 strategy-market hypotheses pooled from factor_combo_*.csv. Family-wide BH-FDR. **Only q=0.10 survivors are citable** (claims.yaml policy). t-stats use n_years-1 dof (annual observations — conservative).

Survivors: **0 at q=0.10**, 0 at q=0.05, of 12 tested.

| market | combo | n | yrs | edge | t | p | FDR q=.10 | q=.05 |
|---|---|---|---|---|---|---|---|---|
| US | not_distress (control) | 6428 | 10 | -2.1 | -2.42 | 0.0388 | — | — |
| US | low_asset_growth (control) | 11649 | 17 | +1.3 | -2.24 | 0.0399 | — | — |
| US | roce_plus + debt_reduction | 59 | 13 | +13.2 | +1.52 | 0.1547 | — | — |
| US | piotroski + debt_reduction | 228 | 15 | +13.4 | +1.10 | 0.2898 | — | — |
| INDIA | piotroski + debt_reduction | 44 | 8 | +8.4 | +1.05 | 0.3287 | — | — |
| INDIA | debt_reduction | 205 | 8 | +4.3 | +1.05 | 0.3300 | — | — |
| INDIA | roce_plus | 50 | 7 | +2.3 | +0.87 | 0.4202 | — | — |
| INDIA | piotroski | 50 | 8 | +5.2 | +0.85 | 0.4260 | — | — |
| US | roce_plus | 607 | 16 | +3.8 | -0.81 | 0.4332 | — | — |
| US | debt_reduction | 1219 | 16 | +6.7 | +0.16 | 0.8768 | — | — |
| US | piotroski | 1314 | 16 | +5.6 | -0.15 | 0.8822 | — | — |
| US | piotroski + roce_plus | 186 | 13 | +6.8 | +0.14 | 0.8932 | — | — |

Interpretation: a — in the FDR column does not mean the effect is zero; it means this grid, searched this widely, cannot distinguish it from selection noise. Deflated-Sharpe helper (`deflated_sharpe`) is available for analyses with full return series.
