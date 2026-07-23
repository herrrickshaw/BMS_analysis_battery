#!/usr/bin/env python3
# watchlist_viz.py
# ================
# Three images for the morning digest, techniques lifted from the open-source
# screener ecosystem (user research request, 2026-07-23):
#
#   treemap_png   Finviz-style squarified treemap (openalgo-heatmap's approach):
#                 tiles grouped market → sector, AREA = median USD turnover
#                 (tradeability), COLOUR = 1d return on the brand ramp. One
#                 image answers "where is today's action, and can I trade it?"
#   rrg_png       Relative Rotation Graph (Julius de Kempenaer, as approximated
#                 by RRGPy/RRG-Lite): each dot is one sector's equal-weight
#                 basket vs its market's equal-weight benchmark, RS-Ratio ×
#                 RS-Momentum, with 5-session tails. Quadrants: Leading /
#                 Weakening / Lagging / Improving.
#   breadth_png   StockBee-style breadth (stock-vcpscreener): % of names above
#                 EMA50 per market, last 30 sessions. Free from the digest's
#                 own zone engine — breadth IS the zone series aggregated.
#
# matplotlib (Agg) + numpy only. The squarified layout is hand-rolled (~30
# lines) rather than adding a `squarify` dependency — check_deps stays honest.
#
# All three fail SOFT: any exception returns None and the digest ships without
# that image. A missing chart is a visible gap; a crashed mailer is a missing
# morning.

from __future__ import annotations

import io
import math
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# smart-investing.in palette (same as the digest HTML)
NAVY, ICE, TEAL, RED, SLATE = "#0B2F4A", "#eef4f6", "#16a085", "#ca3433", "#5f6368"

MARKETS = ("IN", "US", "JP", "KR", "EU")
FLAG = {"IN": "India", "US": "US", "JP": "Japan", "KR": "Korea", "EU": "Europe"}


def _ramp(pct: Optional[float]) -> str:
    """1d% → colour: RED (≤-4) → neutral grey (0) → TEAL (≥+4)."""
    if pct is None or not np.isfinite(pct):
        return "#c9d4da"
    t = max(-4.0, min(4.0, pct)) / 4.0            # -1..1
    def lerp(a, b, f):
        return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))
    neutral, teal, red = (215, 222, 227), (22, 160, 133), (202, 52, 51)
    rgb = lerp(neutral, teal, t) if t >= 0 else lerp(neutral, red, -t)
    return "#%02x%02x%02x" % rgb


# ── squarified treemap layout (Bruls/Huizing/van Wijk, as in openalgo-heatmap) ─
def _worst(row: List[float], length: float) -> float:
    """Worst tile aspect ratio if `row` (areas) is laid along a side of `length`.

    Row thickness t = sum/length; each tile's extent is area/t, so aspect =
    max(t²/area, area/t²). The first version of this compared AREA against
    LENGTH directly — dimensionally wrong — and every row degenerated into a
    full-width strip (caught on the first rendered image)."""
    s = sum(row)
    if not s or not length:
        return float("inf")
    t = s / length
    return max(max(t * t / r, r / (t * t)) for r in row if r > 0)


def _squarify(sizes: List[float], x: float, y: float, w: float, h: float) -> List[Tuple]:
    """Return [(x, y, w, h), ...] matching `sizes` (descending, sum == w*h)."""
    rects = []
    sizes = [max(float(v), 1e-9) for v in sizes]
    while sizes:
        length = min(w, h)
        row = [sizes.pop(0)]
        while sizes and _worst(row + [sizes[0]], length) <= _worst(row, length):
            row.append(sizes.pop(0))
        s = sum(row)
        if w >= h:                                  # row occupies a vertical band
            bw = s / h if h else 0
            ry = y
            for r in row:
                rh = r / bw if bw else 0
                rects.append((x, ry, bw, rh))
                ry += rh
            x += bw
            w -= bw
        else:                                       # horizontal band
            bh = s / w if w else 0
            rx = x
            for r in row:
                rw = r / bh if bh else 0
                rects.append((rx, y, rw, bh))
                rx += rw
            y += bh
            h -= bh
    return rects


def treemap_png(rows: List[dict]) -> Optional[bytes]:
    try:
        priced = [r for r in rows if not r.get("missing") and r.get("d1") is not None
                  and (r.get("turn_usd") or 0) > 0]
        if len(priced) < 20:
            return None
        # panel widths follow each market's total sqrt-turnover but are clamped
        # to [12%, 34%] — unclamped, the US panel ate two-thirds of the figure
        # and Japan/Korea became unreadable slivers.
        raw = [max(1e-9, sum(math.sqrt(r["turn_usd"])
                             for r in priced if r["market"] == m)) for m in MARKETS]
        tot = sum(raw)
        ratios = [min(0.34, max(0.12, v / tot)) for v in raw]
        fig, axes = plt.subplots(1, len(MARKETS), figsize=(13, 4.6),
                                 gridspec_kw={"width_ratios": ratios})
        fig.patch.set_facecolor(ICE)
        for ax, mkt in zip(np.atleast_1d(axes), MARKETS):
            ax.set_facecolor("white")
            g = sorted([r for r in priced if r["market"] == mkt],
                       key=lambda r: -r["turn_usd"])[:40]      # top-40 by turnover
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("#dfe7ec")
            ax.set_title(FLAG[mkt], fontsize=9, color=NAVY, fontweight="bold", pad=4)
            if not g:
                continue
            # sqrt-compress areas: raw turnover would let one mega-cap eat the
            # panel (the openalgo-heatmap demo has the same problem with AAPL)
            sizes = np.array([math.sqrt(r["turn_usd"]) for r in g], dtype=float)
            sizes = sizes / sizes.sum() * 100 * 100
            for (x, y, w, h), r in zip(_squarify(list(sizes), 0, 0, 100, 100), g):
                ax.add_patch(plt.Rectangle((x, y), w, h, lw=0.7, ec="white",
                                           fc=_ramp(r["d1"])))
                if w * h > 250:                     # label only readable tiles
                    ax.text(x + w / 2, y + h / 2,
                            f'{r["symbol"][:9]}\n{r["d1"]:+.1f}%',
                            ha="center", va="center", fontsize=min(8, 1.1 * math.sqrt(w * h) / 4),
                            color="white" if abs(r["d1"]) > 1.2 else NAVY)
            ax.set_xlim(0, 100); ax.set_ylim(0, 100)
            ax.invert_yaxis()
        fig.suptitle("Market map — tile area = median $ turnover (tradeability), colour = 1d move",
                     fontsize=10, color=NAVY, y=0.99)
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, facecolor=ICE)
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        plt.close("all")
        return None


# ── RRG ──────────────────────────────────────────────────────────────────────
def _close_matrix(frames: Dict[tuple, pd.DataFrame], rows: List[dict],
                  mkt: str, bars: int = 90) -> pd.DataFrame:
    """Wide date × symbol close matrix for one market's priced rows."""
    cols = {}
    for r in rows:
        if r["market"] != mkt or r.get("missing"):
            continue
        df = frames.get((mkt, r["symbol"]))
        if df is None:
            continue
        d = df
        for c in ("Date", "date", "price_date"):
            if c in d.columns:
                d = (d.assign(_dt=pd.to_datetime(d[c], errors="coerce"))
                       .dropna(subset=["_dt"]).set_index("_dt"))
                break
        if not isinstance(d.index, pd.DatetimeIndex):
            continue
        c_ = pd.to_numeric(d["Close"], errors="coerce").dropna().tail(bars)
        if len(c_) >= 40:
            cols[r["symbol"]] = c_[~c_.index.duplicated(keep="last")]
    if len(cols) < 10:
        return pd.DataFrame()
    return pd.DataFrame(cols).sort_index().ffill(limit=3)


def rrg_png(rows: List[dict], frames: Dict[tuple, pd.DataFrame]) -> Optional[bytes]:
    try:
        fig, axes = plt.subplots(2, 3, figsize=(13, 8.4))
        fig.patch.set_facecolor(ICE)
        axes = axes.ravel()
        drawn = 0
        for ax, mkt in zip(axes, MARKETS):
            ax.set_facecolor("white")
            wide = _close_matrix(frames, rows, mkt)
            ax.set_title(FLAG[mkt], fontsize=10, color=NAVY, fontweight="bold")
            if wide.empty:
                ax.text(0.5, 0.5, "insufficient data", transform=ax.transAxes,
                        ha="center", color=SLATE, fontsize=9)
                continue
            # keep only dates where most names have data — the union calendar's
            # early rows hold 1-2 names and would skew the benchmark
            wide = wide[wide.notna().mean(axis=1) >= 0.6]
            if len(wide) < 30:
                ax.text(0.5, 0.5, "insufficient data", transform=ax.transAxes,
                        ha="center", color=SLATE, fontsize=9)
                continue
            # normalise each name to its own FIRST VALID bar (bfill picks it);
            # dividing by iloc[0] of the union calendar NaN'd 320/322 columns
            norm = wide / wide.bfill().iloc[0]
            bench = norm.mean(axis=1, skipna=True)
            sec_of = {r["symbol"]: r.get("sector", "Unclassified") for r in rows
                      if r["market"] == mkt}
            sectors = {}
            for sym in wide.columns:
                sectors.setdefault(sec_of.get(sym, "Unclassified"), []).append(sym)
            pts = []
            for sec, syms in sectors.items():
                if len(syms) < 3 or sec == "Unclassified":
                    continue
                idx = norm[syms].mean(axis=1, skipna=True)
                rel = (idx / bench).dropna()
                if len(rel) < 30:
                    continue
                # JdK approximation (RRGPy-style): ratio = rel vs its own 21-bar
                # mean (≈100-centred); momentum = 5-bar rate of change of ratio
                ratio = (100 * rel / rel.rolling(21).mean()).rolling(5).mean()
                mom = (100 * ratio / ratio.shift(5)).rolling(5).mean()
                tail = pd.DataFrame({"r": ratio, "m": mom}).dropna().tail(5)
                # clip the tail to the plot frame — US daily series are noisy
                # enough that a wandering tail scribbles across the panel
                tail = tail[(tail["r"].between(94, 106)) & (tail["m"].between(94, 106))]
                if len(tail) < 2:
                    continue
                # a tiny basket 12+ points from centre is noise, not rotation
                if abs(tail["r"].iloc[-1] - 100) > 12 or abs(tail["m"].iloc[-1] - 100) > 12:
                    continue
                pts.append((sec, tail))
            # rank by distance from centre so labels go to the movers
            pts.sort(key=lambda p: -((p[1]["r"].iloc[-1] - 100) ** 2
                                     + (p[1]["m"].iloc[-1] - 100) ** 2))
            for sec, tail in pts[:10]:
                lead = tail["r"].iloc[-1] >= 100
                up = tail["m"].iloc[-1] >= 100
                col = TEAL if (lead and up) else (RED if (not lead and not up)
                                                 else "#d35400" if lead else "#2980b9")
                ax.plot(tail["r"], tail["m"], lw=1, color=col, alpha=0.55)
                ax.scatter(tail["r"].iloc[-1], tail["m"].iloc[-1], s=26, color=col, zorder=3)
                ax.annotate(sec[:14], (tail["r"].iloc[-1], tail["m"].iloc[-1]),
                            fontsize=7, color=NAVY, xytext=(3, 3),
                            textcoords="offset points")
            ax.axhline(100, color="#cfdde6", lw=1)
            ax.axvline(100, color="#cfdde6", lw=1)
            ax.set_xlim(94, 106); ax.set_ylim(94, 106)   # fixed frame, like real RRGs
            ax.tick_params(labelsize=7, colors=SLATE)
            for sp in ax.spines.values():
                sp.set_color("#dfe7ec")
            drawn += 1
        axes[5].axis("off")
        axes[5].text(0.05, 0.75, "Quadrants", fontsize=10, color=NAVY, fontweight="bold")
        for i, (lab, col) in enumerate((("Leading (↑ strength, ↑ momentum)", TEAL),
                                        ("Weakening (strong, rolling over)", "#d35400"),
                                        ("Lagging (weak, still fading)", RED),
                                        ("Improving (weak, turning up)", "#2980b9"))):
            axes[5].text(0.05, 0.58 - 0.14 * i, "● " + lab, fontsize=8.5, color=col)
        axes[5].text(0.05, 0.02, "Sector basket vs market equal-weight benchmark\n"
                                 "RS-Ratio (x) × RS-Momentum (y), 5-session tails\n"
                                 "JdK approximation per RRGPy / RRG-Lite",
                     fontsize=7.5, color=SLATE)
        if not drawn:
            plt.close(fig)
            return None
        fig.suptitle("Sector rotation (RRG) — right of centre = outperforming its market; "
                     "above = gaining momentum", fontsize=10, color=NAVY, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, facecolor=ICE)
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        plt.close("all")
        return None


# ── breadth ──────────────────────────────────────────────────────────────────
def breadth_png(rows: List[dict], frames: Dict[tuple, pd.DataFrame],
                zone_series_fn) -> Optional[bytes]:
    try:
        fig, axes = plt.subplots(1, len(MARKETS), figsize=(13, 2.1), sharey=True)
        fig.patch.set_facecolor(ICE)
        drawn = 0
        for ax, mkt in zip(np.atleast_1d(axes), MARKETS):
            ax.set_facecolor("white")
            series = []
            for r in rows:
                if r["market"] != mkt or r.get("missing"):
                    continue
                df = frames.get((mkt, r["symbol"]))
                z = zone_series_fn(df) if df is not None else None
                if z is not None and len(z) >= 30:
                    series.append((z != "SELL").tail(30).astype(float))
            ax.set_title(FLAG[mkt], fontsize=9, color=NAVY, fontweight="bold", pad=3)
            ax.set_xticks([])
            for sp in ax.spines.values():
                sp.set_color("#dfe7ec")
            if len(series) < 10:
                ax.text(0.5, 0.5, "n/a", transform=ax.transAxes, ha="center",
                        color=SLATE, fontsize=8)
                continue
            # align on dates; breadth = share of names above EMA50 that session
            b = (pd.concat(series, axis=1).tail(30).mean(axis=1, skipna=True) * 100)
            b = b.dropna()
            col = TEAL if b.iloc[-1] >= 50 else RED
            ax.fill_between(range(len(b)), b.values, 50, alpha=0.18, color=col)
            ax.plot(range(len(b)), b.values, lw=1.4, color=col)
            ax.axhline(50, color="#cfdde6", lw=1)
            ax.scatter([len(b) - 1], [b.iloc[-1]], s=18, color=col, zorder=3)
            ax.annotate(f"{b.iloc[-1]:.0f}%", (len(b) - 1, b.iloc[-1]),
                        fontsize=8, color=col, fontweight="bold",
                        xytext=(-2, 5), textcoords="offset points", ha="right")
            ax.set_ylim(0, 100)
            ax.tick_params(labelsize=7, colors=SLATE)
            drawn += 1
        if not drawn:
            plt.close(fig)
            return None
        fig.suptitle("Breadth — % of tracked names above EMA50 (non-sell zone), last 30 sessions",
                     fontsize=9.5, color=NAVY, y=1.02)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, facecolor=ICE, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        plt.close("all")
        return None


def build_all(rows: List[dict], frames: Dict[tuple, pd.DataFrame],
              zone_series_fn) -> Dict[str, bytes]:
    """{'treemap'|'rrg'|'breadth': png_bytes} — only the ones that rendered."""
    out = {}
    for name, png in (("treemap", treemap_png(rows)),
                      ("rrg", rrg_png(rows, frames)),
                      ("breadth", breadth_png(rows, frames, zone_series_fn))):
        if png:
            out[name] = png
    return out
