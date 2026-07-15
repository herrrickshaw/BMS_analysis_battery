#!/usr/bin/env python3
"""
verify_f_band_us.py — reconcile today's F-band result with the 2026-07-09 backtest.

THE CONTRADICTION
-----------------
project_piotroski_backtests recorded, as settled fact:
    "US Piotroski is INVERTED: high-F (>=7) lags baseline ~4pp on BOTH mean and
     median at 126d and 252d; weak 0-3 band (esp F=0) leads."
Today's sweep found the median FAVOURING high-F. Both cannot be right, and the median
is the statistic both analyses claim to trust.

Two candidate confounds in MY result, tested here by removing them:
  1. My `canonical` vector is Piotroski 9 PLUS the 3-point ROCE block — so my "strong
     band" was a quality-tilted score, not F>=7. I may have measured Piotroski+ROCE
     and called it Piotroski.
  2. I did not winsorize. The prior work calls it essential ("raw F=4 mean was +198%
     from a few lottery movers").

This runs PURE Piotroski (ROCE weighted 0) with 1/99 winsorization per rebalance.

RESULT — the prior claim is HALF right, and my earlier result was distorted by
winsorization, NOT by ROCE:
    baseline: mean +17.5%  median +1.2%
    F 0-3 weak    n=714    mean -1.5pp   median -9.2pp
    F 4-6 mid     n=1854   mean +1.7pp   median +2.5pp
    F 7-9 strong  n=726    mean -2.7pp   median +1.2pp

  * MEAN: high-F lags -2.7pp -> CONFIRMS the prior direction (they said ~-4pp).
  * MEDIAN: high-F LEADS +1.2pp -> CONTRADICTS "lags on both".
  * "Weak band leads" is contradicted outright: weak is the WORST cell on the median
    (-9.2pp) and only looks good on the mean because of the lottery tail the prior
    work itself identified.
  * The true shape is an INVERTED-U — mid-F beats both ends on both statistics. That
    is neither "works" nor "inverted".

WHAT DISTORTED MY EARLIER RESULT (measured, not guessed):
                        weak median  strong median  weak mean  strong mean
    canonical, raw         -8.1%        +4.4%        26.1%       15.6%
    pure F, winsorized     -8.1%        +2.4%        16.0%       14.8%
The MEDIANS barely move => excluding ROCE changed little; my banding was NOT a ROCE
tilt. Winsorization is the whole story: the weak band's mean collapses 26.1 -> 16.0
and the mean "inversion" shrinks from 10.5pp to 1.2pp. So "US Piotroski is INVERTED"
is substantially a WINSORIZATION ARTEFACT — which the prior work's own note predicted
and then recorded the headline anyway.

LIMIT ON MY SIDE: 597 large-cap-biased US names vs their 19 markets / 24,739
companies. Where we disagree, breadth is theirs. But they did not cut by liquidity,
and today's gradient (+14.4% small / -7.3% large) means an aggregate F-band number
averages opposite behaviour at the two ends.
"""
