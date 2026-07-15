#!/usr/bin/env python3
"""
size_vs_liquidity_us.py — is the F-score edge about LIQUIDITY or SIZE?

THE PROBLEM WITH EVERY TIER CUT MADE ON 2026-07-15
--------------------------------------------------
All of them ranked on TURNOVER alone, and turnover correlates with market cap at
+0.797 here. Amihud (2002) and Fang, Noe & Tice (2009) BOTH control for size — Amihud
because the illiquidity premium and the small-firm effect are famously entangled,
Fang/Noe/Tice via LOG_BVTA in every regression. We skipped that control and then read
the gradient as SIZE ("the edge is in small caps") because that is the conventional
story. This double-sorts liquidity WITHIN size to separate them.

Market cap is point-in-time: last close x shares as FILED before the rebalance (EDGAR
`filed`), never today's share count.

RESULT — THE EDGE TRACKS ILLIQUIDITY, NOT SIZE:
    size       liquidity   n     F>=70    F<40     edge
    SMALL_CAP  ILLIQ      819    +7.2%   -6.6%   +13.8%
    SMALL_CAP  LIQUID     818    -1.8%   -9.6%    +7.7%
    LARGE_CAP  ILLIQ      818    +8.2%  -25.6%   +33.7%   <- STRONGEST
    LARGE_CAP  LIQUID     818    +3.6%   +5.3%    -1.7%   <- only negative cell

Within BOTH size buckets, illiquid beats liquid. The strongest edge is in LARGE caps
that are ILLIQUID (+33.7pp) — not small caps at all.

SO THE 2026-07-15 HEADLINE WAS WRONG. "The F-score edge is in SMALL CAPS" should read
"the edge is in ILLIQUID names, regardless of size". Turnover tiers conflated the two
and the wrong variable was named. This is also a BETTER match to Piotroski (2000), who
specified "small, ILLIQUID, low-analyst-coverage value stocks" — illiquidity was always
in the claim; three attributes were collapsed into one and the wrong one was picked.

MECHANISM, legible in the strongest cell: illiquid large-caps with weak fundamentals
CRASH (F<40 median -25.6%) — value traps, low float, distressed names institutions
cannot exit. The F-score identifies them. Meanwhile the only negative cell is
LARGE + LIQUID (-1.7%): the most efficiently priced corner of the most efficient
market on earth, where no edge should survive, and none does.

DOES NOT CHANGE THE COST MODEL: illiquid names are illiquid whatever their market cap,
so the ~$300-500k capacity holds. For illiquid LARGE caps, low float may bite harder
than turnover alone suggests.

CAVEATS: 818 per cell across 9 CLUSTERED rebalances, no standard errors.
LARGE_CAP+ILLIQ is an unusual segment (low float, post-lockup, closely held) that may
not be reachable in practice. corr(turnover, mcap)=+0.797 is high — separable, but the
cells are not cleanly orthogonal.
"""
