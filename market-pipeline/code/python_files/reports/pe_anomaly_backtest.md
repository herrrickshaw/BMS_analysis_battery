# PE anomaly backtests — India

Universe: 1458 NSE names, monthly 2017-01-31 → 2026-06-30. Annual PIT EPS (filed date, else fy_end+90d); adjusted closes; PE winsorized to [1.0, 200.0]. Survivorship-biased universe — read SPREADS, not levels.

## A. Sector-relative PE — do anomalies correct?

109 monthly formations; quintile 1 = CHEAPEST vs own industry.

| horizon | Q1 cheap | Q2 | Q3 | Q4 | Q5 rich | Q1−Q5 | t (de-overlapped) |
|---|---|---|---|---|---|---|---|
| 1M | +2.29% | +1.92% | +1.75% | +1.54% | +1.44% | **+0.85%** | 2.82 |
| 3M | +6.06% | +5.27% | +4.05% | +3.83% | +3.47% | **+2.60%** | 2.86 |
| 6M | +11.85% | +10.15% | +7.58% | +7.26% | +6.59% | **+5.26%** | 2.47 |

**Sector-level stretch (median PE z vs own 36M history) → forward 3M sector return:**

- stretched rich (z > +1.5): +7.34% (n=377 sector-months)
- neutral (|z| ≤ 0.5): +6.96% (n=601)
- stretched cheap (z < −1.5): +9.37% (n=180)

## B. PE trends vs company performance

12M multiple change × 12M EPS delivery → forward returns (equal-weight, monthly formations):

| bucket | n/mo | fwd 3M | fwd 6M |
|---|---|---|---|
| PE↑ EPS↑ (earned re-rating) | 105 | +5.56% | +11.55% |
| PE↑ EPS↓ (hope rally) | 192 | +5.15% | +10.83% |
| PE↓ EPS↑ (cheapening on delivery) | 256 | +3.52% | +7.47% |
| PE↓ EPS↓ (deserved de-rating) | 76 | +2.67% | +7.71% |

**Do high-PE names deliver faster subsequent EPS growth (next 12M, log growth)?**

| PE quintile (1=cheap) | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| subsequent EPS growth | -37.4% | -11.5% | -0.3% | +9.8% | +33.7% |
