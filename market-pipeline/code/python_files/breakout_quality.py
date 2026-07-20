# breakout_quality.py
# ===================
# Darvas breakout scoring: EMA-50 trend filter + a 0-100 breakout QUALITY score
# built from compression, relative volume, and candle-body participation.
#
# WHY THIS RECOMPUTES INSTEAD OF READING THE SCAN'S COLUMNS
# ─────────────────────────────────────────────────────────
# The obvious implementation is to read Darvas_Signal / Box_Top / Box_Bottom off
# the scan workbook and filter them. That would be wrong right now: on the
# 2026-07-21 Korea workbook, 2,461 of 2,472 rows labelled BREAKDOWN_SELL do not
# satisfy `close < box_bottom` using the box values printed in the SAME row, and
# 306 rows sit ABOVE box_top while labelled a breakdown. Position_in_Box% reads
# -1990.9 where it is defined to be 0-100. The signal column disagrees with its
# own inputs, which points at a row misalignment upstream, not at the box maths.
#
# Filtering a corrupted signal produces a smaller corrupted signal. So everything
# here is derived from raw OHLC, and the box is recomputed. Correct signals are a
# by-product, which also makes this a cross-check on the scan.
#
# THE FOUR TESTS
# ──────────────
#   1. EMA-50 trend    — price above a RISING 50-EMA. A breakout against a
#                        falling EMA is usually a bounce inside a downtrend.
#   2. Compression     — a box that narrowed before the break. Energy stored in
#                        a tight range is the actual Darvas premise; a break out
#                        of an already-wide range has no coil to release.
#   3. Relative volume — breakout volume vs its own 50-day median. A breakout on
#                        below-average volume has no participation behind it.
#   4. Body            — |close-open| / (high-low). A wide range closing mid-bar
#                        is indecision wearing a breakout's clothes.
#
# Weights are deliberately blunt (30/25/25/20) and stated here rather than
# tuned: nothing in this repo has yet measured which factor predicts forward
# returns on this universe, so a fitted weighting would be false precision.
# factor_tests.sh is where that question gets answered.
#
#   from breakout_quality import score_breakout
#   q = score_breakout(ohlc_df)      # dict, or None if history is too short

from __future__ import annotations

from typing import Optional

import pandas as pd

DARVAS_CONFIRM = 3
EMA_SPAN = 50
VOL_LOOKBACK = 50
MIN_BARS = 60

WEIGHTS = {"trend": 30, "compression": 25, "volume": 25, "body": 20}

# A breakout scoring below this is a signal you would not act on.
GOOD_SCORE = 60


def _num(df: pd.DataFrame, col: str) -> Optional[pd.Series]:
    if col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    return s if s.notna().any() else None


def darvas_box(df: pd.DataFrame, confirm: int = DARVAS_CONFIRM) -> dict:
    """Box top/bottom from history EXCLUDING the current bar.

    Excluding the current bar is not a detail — if today's high can define the
    box top, price can never exceed it and a breakout becomes unrepresentable.
    (Symmetrically, including it makes breakdowns undetectable.) The box must be
    formed from settled history and then tested against today.
    """
    # Trim trailing bars with no close first. Without this, current becomes NaN,
    # every comparison is False, and the box silently reports IN_BOX — a wrong
    # answer that looks like a real one. Same class of bug as the .fillna(0) it
    # was written to avoid, just failing quiet instead of loud.
    try:
        _c = pd.to_numeric(df["Close"], errors="coerce")
        _last = _c.last_valid_index()
        if _last is None:
            return {}
        df = df.loc[:_last]
    except Exception:
        return {}

    highs = _num(df, "High")
    lows = _num(df, "Low")
    closes = _num(df, "Close")
    if highs is None or lows is None or closes is None or len(df) < confirm + 5:
        return {}

    h, l = highs.tolist()[:-1], lows.tolist()[:-1]
    current = float(closes.iloc[-1])
    n = len(h)

    top_idx = top = None
    for i in range(n - confirm - 1, -1, -1):
        c = h[i]
        if not c or c != c:
            continue
        w = h[i + 1: i + 1 + confirm]
        if len(w) == confirm and all(x < c for x in w):
            top_idx, top = i, c
            break
    if top is None:
        return {}

    seg = l[top_idx:]
    bottom = None
    for i in range(len(seg) - confirm):
        c = seg[i]
        if not c or c != c:
            continue
        w = seg[i + 1: i + 1 + confirm]
        if len(w) == confirm and all(x > c for x in w):
            bottom = c
            break
    if bottom is None:
        valid = [x for x in seg if x and x == x]
        bottom = min(valid) if valid else None
    if bottom is None or bottom <= 0:
        return {}

    signal = ("BREAKOUT_BUY" if current > top else
              "BREAKDOWN_SELL" if current < bottom else "IN_BOX")
    rng = top - bottom
    return {"box_top": top, "box_bottom": bottom, "current": current,
            "signal": signal, "box_width_pct": (rng / bottom * 100) if bottom else None,
            "box_start_idx": top_idx, "box_bars": len(df) - 1 - top_idx,
            "position_in_box_pct": ((current - bottom) / rng * 100) if rng else None}


def _trend(df: pd.DataFrame) -> dict:
    """EMA-50: price above it, and the EMA itself rising."""
    closes = _num(df, "Close")
    if closes is None or len(closes) < EMA_SPAN:
        return {"pts": 0, "detail": "insufficient history for EMA-50"}
    ema = closes.ewm(span=EMA_SPAN, adjust=False).mean()
    last, e_last = float(closes.iloc[-1]), float(ema.iloc[-1])
    e_prev = float(ema.iloc[-6]) if len(ema) > 6 else e_last
    above = last > e_last
    rising = e_last > e_prev
    dist = (last / e_last - 1) * 100 if e_last else 0.0

    # Both conditions carry weight; above-but-falling is the classic false
    # breakout, so it scores materially lower than above-and-rising.
    pts = (0.6 if above else 0.0) + (0.4 if rising else 0.0)
    # Extended >20% above the EMA is chasing, not confirming.
    if above and dist > 20:
        pts *= 0.7
    return {"pts": pts, "ema50": e_last, "above_ema": above, "ema_rising": rising,
            "pct_above_ema": dist,
            "detail": f"{'above' if above else 'below'} EMA50, "
                      f"{'rising' if rising else 'falling'}"}


def _compression(df: pd.DataFrame, box: dict) -> dict:
    """Did the range tighten into the breakout?

    Compares the box's own width to the range 20 bars before it formed. A ratio
    below 1 means the market coiled; above 1 means it was already expanding and
    the 'breakout' is just continuation of a widening range.
    """
    highs, lows = _num(df, "High"), _num(df, "Low")
    if highs is None or lows is None or not box:
        return {"pts": 0, "detail": "n/a"}
    start = box.get("box_start_idx")
    if start is None or start < 20:
        return {"pts": 0.5, "detail": "insufficient pre-box history"}

    pre_h, pre_l = highs.iloc[start - 20:start], lows.iloc[start - 20:start]
    if pre_h.empty or pre_l.empty:
        return {"pts": 0.5, "detail": "n/a"}
    pre_width = (pre_h.max() - pre_l.min()) / pre_l.min() * 100 if pre_l.min() else None
    box_width = box.get("box_width_pct")
    if not pre_width or not box_width:
        return {"pts": 0.5, "detail": "n/a"}

    ratio = box_width / pre_width
    pts = 1.0 if ratio <= 0.6 else 0.75 if ratio <= 0.8 else 0.5 if ratio <= 1.0 else 0.2
    return {"pts": pts, "compression_ratio": ratio, "box_width_pct": box_width,
            "detail": f"box {box_width:.1f}% vs prior {pre_width:.1f}% (x{ratio:.2f})"}


def _volume(df: pd.DataFrame) -> dict:
    """Breakout-bar volume against its own 50-day median.

    Median, not mean: a single block trade in the lookback would lift a mean and
    make every subsequent day look weak by comparison.
    """
    vol = _num(df, "Volume")
    if vol is None or len(vol) < 10:
        return {"pts": 0.5, "detail": "no volume data"}
    hist = vol.iloc[-(VOL_LOOKBACK + 1):-1]
    med = hist.median()
    if not med or med <= 0:
        return {"pts": 0.5, "detail": "no usable volume history"}
    rvol = float(vol.iloc[-1]) / float(med)
    pts = 1.0 if rvol >= 2.0 else 0.8 if rvol >= 1.5 else 0.55 if rvol >= 1.0 else 0.2
    return {"pts": pts, "rel_volume": rvol, "detail": f"{rvol:.2f}x median volume"}


def _body(df: pd.DataFrame) -> dict:
    """Candle body as a share of the bar's range."""
    o, h, l, c = (_num(df, x) for x in ("Open", "High", "Low", "Close"))
    if any(x is None for x in (o, h, l, c)):
        return {"pts": 0.5, "detail": "no OHLC detail"}
    O, H, L, C = (float(x.iloc[-1]) for x in (o, h, l, c))
    rng = H - L
    if rng <= 0:
        return {"pts": 0.5, "detail": "zero-range bar"}
    body = abs(C - O) / rng
    closed_up = C >= O
    pts = (1.0 if body >= 0.7 else 0.75 if body >= 0.5 else 0.45 if body >= 0.3 else 0.15)
    if not closed_up:
        pts *= 0.5          # a red body on a breakout bar is a rejection
    return {"pts": pts, "body_pct": body * 100, "closed_up": closed_up,
            "detail": f"body {body*100:.0f}% of range, closed {'up' if closed_up else 'DOWN'}"}


def score_breakout(df: pd.DataFrame) -> Optional[dict]:
    """Recomputed signal + 0-100 quality score. None if history is too short."""
    if df is None or len(df) < MIN_BARS:
        return None
    box = darvas_box(df)
    if not box:
        return None

    t, comp, v, b = _trend(df), _compression(df, box), _volume(df), _body(df)
    score = (t["pts"] * WEIGHTS["trend"] + comp["pts"] * WEIGHTS["compression"]
             + v["pts"] * WEIGHTS["volume"] + b["pts"] * WEIGHTS["body"])

    out = dict(box)
    out.update({
        "quality_score": round(score, 1),
        "quality_grade": ("A" if score >= 80 else "B" if score >= GOOD_SCORE
                          else "C" if score >= 40 else "D"),
        "trend_pts": round(t["pts"] * WEIGHTS["trend"], 1),
        "compression_pts": round(comp["pts"] * WEIGHTS["compression"], 1),
        "volume_pts": round(v["pts"] * WEIGHTS["volume"], 1),
        "body_pts": round(b["pts"] * WEIGHTS["body"], 1),
        "ema50": t.get("ema50"), "above_ema50": t.get("above_ema"),
        "ema50_rising": t.get("ema_rising"), "pct_above_ema50": t.get("pct_above_ema"),
        "compression_ratio": comp.get("compression_ratio"),
        "rel_volume": v.get("rel_volume"), "body_pct": b.get("body_pct"),
        "why": "; ".join(x["detail"] for x in (t, comp, v, b)),
    })
    # The EMA filter is reported separately from the score so a caller can gate
    # on trend without silently discarding a high-quality setup in a downtrend.
    out["ema_confirmed"] = bool(t.get("above_ema") and t.get("ema_rising"))
    out["actionable"] = bool(out["signal"] == "BREAKOUT_BUY"
                             and out["ema_confirmed"]
                             and score >= GOOD_SCORE)
    return out
