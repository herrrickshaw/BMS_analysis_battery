# Cost-adjusted intimation drift — 2026-07-23 07:09

Per-event, PIT costs: Corwin-Schultz spread + Amihud impact from the
120 trading days before each intimation; commissions 0.2% round trip. Gross = CAR drift [+2, ex-1]
(abnormal vs market median — the universe-level bias caveat from
PIT_EVENT_STUDIES.md applies to gross AND net alike).

A position is EXECUTABLE in an event only if it is <=10% of that
name's median daily turnover (standard participation cap) — linear
impact estimates past that are fiction, and so is the fill. Skipped
events are reported, not averaged in.

| kind | position | executable | gross (med) | cost (med) | net (med) | net hit% | skipped (>10% ADV) |
|---|---|---|---|---|---|---|---|
| bonus | Rs 1L | 271 | +9.57% | 1.00% | +7.96% | 73% | 11/282 |
| bonus | Rs 10L | 211 | +8.31% | 0.94% | +7.28% | 73% | 71/282 |
| bonus | Rs 50L | 141 | +5.29% | 0.93% | +4.73% | 68% | 141/282 |
| bonus | Rs 2Cr | 84 | +5.16% | 0.87% | +4.40% | 69% | 198/282 |
| split | Rs 1L | 223 | +15.07% | 1.12% | +13.73% | 80% | 14/237 |
| split | Rs 10L | 157 | +13.71% | 1.05% | +13.14% | 78% | 80/237 |
| split | Rs 50L | 101 | +11.35% | 0.94% | +10.39% | 75% | 136/237 |
| split | Rs 2Cr | 52 | +11.36% | 0.77% | +10.33% | 79% | 185/237 |

Median PIT Corwin-Schultz spread across events: 0.83% · median daily turnover: Rs 4.0Cr

Reading: cost has three parts — spread (size-independent), impact
(scales with position), commissions (flat). Where net stays near
gross at small size but dies at Rs 2Cr, the edge is real but
capacity-constrained (the illiquid-name pattern again). Where net
is negative even at Rs 1L, the spread alone eats the drift.
