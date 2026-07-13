#!/usr/bin/env python3
"""
chart_pattern_cv.py
====================
Classical computer-vision chart-pattern detector.

Derived from patents MY269060 A/B/C "System and method for detecting and
tracking objects... using a deep learning model" (IIIT-Hyderabad, CVIT).

SCOPE NOTE: this does NOT use a trained deep-learning object detector -- that
would need labeled training data this repo doesn't have, and training one is
its own project, not something to fake here. What it borrows from those
patents is the *framing*: treat the price chart as an IMAGE and detect
patterns by visual shape, rather than by numeric OHLC threshold rules the way
scanners/darvas.py does. Concretely:

  1. Render the price series to a rasterised chart image (matplotlib).
  2. Extract the plotted curve's pixel-space peaks/troughs via classical
     image processing (Gaussian smoothing + local-extrema detection on the
     rendered pixels, not the raw numeric series).
  3. Map those pixel-space extrema back to (date, price) via the axes'
     data transform, then match the resulting shape sequence against
     geometric templates for a few well-known chart patterns.

This is a genuine, if modest, image-based technique -- a legitimate
complement to (not a replacement for) the rule-based Darvas scanner.

Usage:
    from chart_pattern_cv import detect_patterns
    hits = detect_patterns(prices)   # prices: pd.Series of closes, DatetimeIndex
    for h in hits:
        print(h["pattern"], h["confidence"], h["key_levels"])
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


@dataclass
class Extremum:
    index: int          # position in the original price series
    date: object         # timestamp
    price: float
    kind: str            # "peak" | "trough"


@dataclass
class PatternHit:
    pattern: str
    confidence: float                 # 0-1, how well the geometry matches the ideal template
    key_levels: dict = field(default_factory=dict)
    extrema: List[Extremum] = field(default_factory=list)


def _rasterize_and_find_extrema(
    prices: pd.Series,
    smoothing_sigma: float = 3.0,
    fig_width_px: int = 1200,
    fig_height_px: int = 500,
) -> List[Extremum]:
    """
    Renders *prices* to an image, then finds local extrema of the plotted
    curve in PIXEL space (smoothed to suppress single-bar noise the way a
    human eye would when visually spotting a pattern), and maps them back to
    (date, price) via the axes' data transform.
    """
    dpi = 100
    fig, ax = plt.subplots(figsize=(fig_width_px / dpi, fig_height_px / dpi), dpi=dpi)
    x = np.arange(len(prices))
    ax.plot(x, prices.values, "-", color="black", linewidth=1.5)
    ax.set_xlim(0, len(prices) - 1)
    # Strip every bit of chart decoration (axis spines/frame, ticks, margins)
    # -- without this, the axes' border is a solid black line at a fixed
    # pixel row, and a per-column argmin() for "the darkest pixel" latches
    # onto that frame instead of the plotted curve, since anti-aliasing can
    # make the thin data line locally lighter than the solid border.
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.canvas.draw()

    # Rasterise to a grayscale numpy array.
    buf = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8)
    w, h = fig.canvas.get_width_height()
    img = buf.reshape(h, w, 4)[:, :, :3].mean(axis=2)  # grayscale

    # For each pixel column, the plotted curve is the darkest pixel (the line
    # is black on a white background) -- recover its row (pixel y-position).
    # `img` is indexed top-down (row 0 = top of image, from the raw buffer),
    # but matplotlib's transData works in bottom-up display coordinates (row
    # 0 = bottom) -- without flipping here, the recovered y-axis comes out
    # inverted (peaks map to troughs and vice versa).
    dark_rows_topdown = img.argmin(axis=0).astype(float)
    dark_rows = (h - 1) - dark_rows_topdown

    # Map pixel-space (col, row) back to data-space (x_data, price) using the
    # axes' inverse data transform, one column at a time.
    inv = ax.transData.inverted()
    cols = np.arange(w)
    data_coords = inv.transform(np.column_stack([cols, dark_rows]))
    x_data = data_coords[:, 0]
    y_data = data_coords[:, 1]
    plt.close(fig)

    # Keep only columns inside the actual plotted axis range (drop margins).
    mask = (x_data >= 0) & (x_data <= len(prices) - 1)
    x_data, y_data = x_data[mask], y_data[mask]
    if len(y_data) < 5:
        return []

    # Smooth in pixel/data space to suppress rendering & single-bar noise
    # before hunting for extrema -- this is the "visual" smoothing a human
    # eye applies when spotting a pattern, done explicitly here.
    smoothed = gaussian_filter1d(y_data, sigma=smoothing_sigma)

    # find_peaks (not argrelextrema) so we can require genuine significance:
    # `distance` rules out extrema closer together than ~2% of the series
    # (no multi-week chart pattern turns on a single day), and `prominence`
    # rules out extrema that don't stand out from the surrounding noise by at
    # least ~4% of the series' total price range. Without both, smoothing
    # alone still lets through the staircase-like micro-extrema that
    # pixel-rounding and small day-to-day noise create on an otherwise flat
    # run -- exactly the false-positive flood this guards against.
    price_range = float(np.max(y_data) - np.min(y_data)) or 1.0
    min_distance = max(5, len(smoothed) // 50)
    min_prominence = price_range * 0.04

    peak_idx, _ = find_peaks(smoothed, distance=min_distance, prominence=min_prominence)
    trough_idx, _ = find_peaks(-smoothed, distance=min_distance, prominence=min_prominence)

    extrema: List[Extremum] = []
    for i in peak_idx:
        orig_i = int(round(x_data[i]))
        orig_i = max(0, min(orig_i, len(prices) - 1))
        extrema.append(Extremum(orig_i, prices.index[orig_i], float(prices.iloc[orig_i]), "peak"))
    for i in trough_idx:
        orig_i = int(round(x_data[i]))
        orig_i = max(0, min(orig_i, len(prices) - 1))
        extrema.append(Extremum(orig_i, prices.index[orig_i], float(prices.iloc[orig_i]), "trough"))

    extrema.sort(key=lambda e: e.index)
    # Collapse consecutive same-kind extrema (keep the more extreme one).
    collapsed: List[Extremum] = []
    for e in extrema:
        if collapsed and collapsed[-1].kind == e.kind:
            keep_new = (e.price > collapsed[-1].price) if e.kind == "peak" else (e.price < collapsed[-1].price)
            if keep_new:
                collapsed[-1] = e
        else:
            collapsed.append(e)
    return collapsed


def _match_double_top_bottom(extrema: List[Extremum], tolerance: float = 0.03) -> List[PatternHit]:
    hits = []
    for i in range(len(extrema) - 2):
        a, mid, b = extrema[i], extrema[i + 1], extrema[i + 2]
        if a.kind == b.kind and a.kind != mid.kind:
            height_diff = abs(a.price - b.price) / max(a.price, b.price)
            if height_diff <= tolerance:
                confidence = round(1.0 - height_diff / tolerance, 3)
                name = "Double Top" if a.kind == "peak" else "Double Bottom"
                hits.append(PatternHit(
                    pattern=name, confidence=confidence,
                    key_levels={"level_1": a.price, "level_2": b.price, "neckline": mid.price},
                    extrema=[a, mid, b],
                ))
    return hits


def _match_head_and_shoulders(extrema: List[Extremum], tolerance: float = 0.05) -> List[PatternHit]:
    hits = []
    for i in range(len(extrema) - 4):
        window = extrema[i:i + 5]
        kinds = [e.kind for e in window]
        if kinds != ["trough", "peak", "trough", "peak", "trough"]:
            continue
        left_shoulder, neck1, head, neck2, right_shoulder = window
        neckline = (neck1.price + neck2.price) / 2
        # A valid head & shoulders needs the neckline BELOW both shoulders --
        # not just below the head. Local extrema in a strongly trending
        # market can otherwise satisfy "head is the highest point" while the
        # troughs between it and the shoulders are still above one shoulder,
        # which isn't a real head-and-shoulders top.
        if not (head.price > left_shoulder.price and head.price > right_shoulder.price
                and neckline < left_shoulder.price and neckline < right_shoulder.price):
            continue
        shoulder_diff = abs(left_shoulder.price - right_shoulder.price) / max(left_shoulder.price, right_shoulder.price)
        if shoulder_diff <= tolerance:
            confidence = round(1.0 - shoulder_diff / tolerance, 3)
            hits.append(PatternHit(
                pattern="Head and Shoulders", confidence=confidence,
                key_levels={
                    "left_shoulder": left_shoulder.price, "head": head.price,
                    "right_shoulder": right_shoulder.price,
                    "neckline": round(neckline, 4),
                },
                extrema=window,
            ))
    return hits


def _match_cup_and_handle(
    prices: pd.Series,
    extrema: List[Extremum],
    handle_max_fraction: float = 0.4,
) -> List[PatternHit]:
    """
    Simplified geometric check: a broad trough (cup) whose two rim peaks are
    close in height, followed by a smaller pullback (handle) that stays in
    the upper portion of the cup's depth before the series ends.
    """
    hits = []
    troughs = [e for e in extrema if e.kind == "trough"]
    peaks = [e for e in extrema if e.kind == "peak"]
    for t in troughs:
        left_rim = next((p for p in reversed(peaks) if p.index < t.index), None)
        right_rim = next((p for p in peaks if p.index > t.index), None)
        if left_rim is None or right_rim is None:
            continue
        rim_diff = abs(left_rim.price - right_rim.price) / max(left_rim.price, right_rim.price)
        cup_depth = right_rim.price - t.price
        if rim_diff > 0.08 or cup_depth <= 0:
            continue
        # Handle: a smaller pullback after the right rim, shallower than the cup.
        after = [e for e in extrema if e.index > right_rim.index and e.kind == "trough"]
        if not after:
            continue
        handle_trough = after[0]
        handle_depth = right_rim.price - handle_trough.price
        if 0 < handle_depth <= cup_depth * handle_max_fraction:
            confidence = round(1.0 - rim_diff / 0.08, 3)
            hits.append(PatternHit(
                pattern="Cup and Handle", confidence=confidence,
                key_levels={
                    "left_rim": left_rim.price, "cup_bottom": t.price,
                    "right_rim": right_rim.price, "handle_bottom": handle_trough.price,
                },
                extrema=[left_rim, t, right_rim, handle_trough],
            ))
    return hits


def detect_patterns(prices: pd.Series) -> List[dict]:
    """
    Detect chart patterns in *prices* (a pandas Series of closes, DatetimeIndex)
    using the image-based extrema-detection pipeline above.

    Returns a list of dicts (pattern, confidence, key_levels, start_date,
    end_date), ranked by confidence, highest first.
    """
    prices = prices.dropna()
    if len(prices) < 20:
        return []

    extrema = _rasterize_and_find_extrema(prices)
    if len(extrema) < 3:
        return []

    hits = (
        _match_double_top_bottom(extrema)
        + _match_head_and_shoulders(extrema)
        + _match_cup_and_handle(prices, extrema)
    )
    hits.sort(key=lambda h: h.confidence, reverse=True)

    return [
        {
            "pattern": h.pattern,
            "confidence": h.confidence,
            "key_levels": {k: round(v, 4) for k, v in h.key_levels.items()},
            "start_date": h.extrema[0].date,
            "end_date": h.extrema[-1].date,
        }
        for h in hits
    ]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CV-based chart pattern detector")
    ap.add_argument("symbol")
    ap.add_argument("--period", default="2y")
    args = ap.parse_args()

    import yfinance as yf
    yf_symbol = args.symbol if "." in args.symbol else f"{args.symbol}.NS"
    data = yf.download(yf_symbol, period=args.period, auto_adjust=True, progress=False)
    close = data["Close"].iloc[:, 0] if hasattr(data["Close"], "columns") else data["Close"]

    for hit in detect_patterns(close):
        print(f"{hit['pattern']:<20} confidence={hit['confidence']:.2f}  "
              f"{hit['start_date'].date()} -> {hit['end_date'].date()}  {hit['key_levels']}")
