#!/usr/bin/env python3
"""
combo_by_tier_us.py — darvas x piotroski7 cut by liquidity tier. UNDERPOWERED; read why.

MOTIVATION
----------
project_piotroski_backtests records the best result the prior work found:
    "Piotroski STANDALONE is inverted BUT as a QUALITY OVERLAY on Darvas breakouts:
     darvas x piotroski7 median edge +9.9pp, 62% win. F-score fails as a stock-picker,
     works as a breakout overlay."
That was measured across the whole US sample with NO liquidity cut. Today's gradient
(F-score edge +14.4% in small caps, -7.3% in large) means an aggregate number may be
averaging opposite behaviour at the two ends. This cuts the combo by tier.

🔴 THE COMBO RESULT HERE IS NOT USABLE — A DESIGN FLAW, NOT A FINDING
--------------------------------------------------------------------
A Darvas breakout is a RARE DAILY EVENT. This samples it on 9 ANNUAL rebalance dates,
catching ~3% of signals (117 breakouts total). The combo cells:
    SMALL n=1    MID n=7    LARGE n=17
n=1 and n=7 are not results. The prior work's backtest_combo_us.py scanned DAILY and
would have had thousands of signals. The LARGE cell (n=17, +9.4pp) lands close to the
prior +9.9pp, which is encouraging as a consistency signal but is ~2 signals/year and
is not claimed here.

FIX: signal on ANY day a breakout fires, score with the F-value PUBLIC at that date
(EDGAR `filed`), hold 252d. Annual snapshots cannot test a daily-event strategy.

WHAT IS WELL-POWERED — and it is new
------------------------------------
The single-screen columns use the full panel (3,588 stock-years, 642 symbols):

    tier     base med   darvas alone   F>=7 alone
    SMALL      -8.1%       -7.5%         +8.0%
    MID        +3.7%      -10.1%         -1.2%
    LARGE      +5.9%      +12.2%         -2.2%

THE TWO SCREENS HAVE OPPOSITE LIQUIDITY GRADIENTS.
  * Piotroski: works SMALL (+8.0), fails LARGE (-2.2) — the gradient reproduced for a
    third time, on a fourth sample.
  * Darvas: the MIRROR IMAGE — +12.2 LARGE, -7.5 SMALL.

This reframes "F-score fails as a stock-picker, works as a breakout overlay": both may
be true AND tier-dependent, with Darvas supplying the edge in large caps and Piotroski
in small. If so the prior +9.9pp combo averages two different mechanisms operating in
different segments — precisely what a liquidity cut exposes and an aggregate hides.

All edges are vs that tier's OWN median, winsorized 1/99 per rebalance (the prior work
calls winsorization essential; without it the lottery tail sets the mean).
"""
