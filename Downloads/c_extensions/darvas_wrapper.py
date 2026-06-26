# darvas_wrapper.py — Python ctypes wrapper for the C Darvas implementation
# ==========================================================================
# Provides the same interface as the Python darvas functions but 100× faster.
# Falls back to pure Python if the .so library is not available.
#
# Usage:
#   from darvas_wrapper import darvas_classify_fast, darvas_walk_forward_fast
#
#   result = darvas_classify_fast(df)       # classify current bar
#   signals = darvas_walk_forward_fast(df)  # walk-forward signal detection

import ctypes
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Load compiled shared library
_LIB_PATH = Path(__file__).parent / "darvas_fast.so"
_lib       = None

if _LIB_PATH.exists():
    try:
        _lib = ctypes.CDLL(str(_LIB_PATH))

        # DarvasResult struct
        class _DarvasResult(ctypes.Structure):
            _fields_ = [
                ("signal",              ctypes.c_int),
                ("box_top",             ctypes.c_double),
                ("box_bottom",          ctypes.c_double),
                ("current_price",       ctypes.c_double),
                ("upside_to_top_pct",   ctypes.c_double),
                ("position_in_box_pct", ctypes.c_double),
                ("data_points",         ctypes.c_int),
            ]

        # DarvasSignal struct
        class _DarvasSignal(ctypes.Structure):
            _fields_ = [
                ("bar_idx",     ctypes.c_int),
                ("entry_price", ctypes.c_double),
                ("box_top",     ctypes.c_double),
                ("box_bottom",  ctypes.c_double),
            ]

        # darvas_classify
        _lib.darvas_classify.argtypes = [
            ctypes.POINTER(ctypes.c_double),  # highs
            ctypes.POINTER(ctypes.c_double),  # lows
            ctypes.POINTER(ctypes.c_double),  # closes
            ctypes.c_int,                     # n
            ctypes.c_int,                     # confirm
            ctypes.c_int,                     # lookback
            ctypes.POINTER(_DarvasResult),    # result
        ]
        _lib.darvas_classify.restype = None

        # darvas_walk_forward
        _lib.darvas_walk_forward.argtypes = [
            ctypes.POINTER(ctypes.c_double),  # highs
            ctypes.POINTER(ctypes.c_double),  # lows
            ctypes.POINTER(ctypes.c_double),  # closes
            ctypes.POINTER(ctypes.c_double),  # volumes (can be NULL)
            ctypes.c_int,                     # n
            ctypes.c_int,                     # confirm
            ctypes.c_int,                     # cooldown
            ctypes.c_double,                  # vol_threshold
            ctypes.POINTER(_DarvasSignal),    # out_signals
            ctypes.c_int,                     # max_signals
        ]
        _lib.darvas_walk_forward.restype = ctypes.c_int

        # zscore_normalize_window
        _lib.zscore_normalize_window.argtypes = [
            ctypes.POINTER(ctypes.c_double),  # data (in-place)
            ctypes.c_int,                     # rows
            ctypes.c_int,                     # cols
        ]
        _lib.zscore_normalize_window.restype = None

        _C_AVAILABLE = True
    except Exception as e:
        print(f"  ⚠️  C library load failed: {e} — falling back to Python")
        _C_AVAILABLE = False
else:
    _C_AVAILABLE = False

# Signal code → string mapping (matches C constants)
_SIGNAL_MAP = {
    0: "NO_BOX",
    1: "IN_BOX",
    2: "BREAKOUT_BUY",
    3: "BREAKDOWN_SELL",
    4: "INSUFFICIENT_DATA",
}


def _to_c_arr(arr: np.ndarray):
    """Convert numpy float64 array to ctypes double pointer."""
    a = np.ascontiguousarray(arr, dtype=np.float64)
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), a


def darvas_classify_fast(df: pd.DataFrame,
                          confirm: int = 3, lookback: int = 60) -> dict:
    """
    Classify the current bar's position relative to the Darvas Box.
    Uses C implementation if available, Python fallback otherwise.

    Same interface as compute_darvas_box() in full_indian_market_scan.py.
    """
    if df is None or df.empty or len(df) < confirm + 5:
        return {"signal": "INSUFFICIENT_DATA", "box_top": None, "box_bottom": None}

    def _find_col(cols, candidates):
        for c in candidates:
            m = next((col for col in cols if c.upper() in col.upper()), None)
            if m: return m
        return None

    h_col = _find_col(df.columns, ["High"])
    l_col = _find_col(df.columns, ["Low"])
    c_col = _find_col(df.columns, ["Close"])
    if not all([h_col, l_col, c_col]):
        return {"signal": "INSUFFICIENT_DATA"}

    highs  = df[h_col].values.astype(np.float64)
    lows   = df[l_col].values.astype(np.float64)
    closes = df[c_col].values.astype(np.float64)
    n      = len(closes)

    if _C_AVAILABLE:
        h_ptr, h_arr = _to_c_arr(highs)
        l_ptr, l_arr = _to_c_arr(lows)
        c_ptr, c_arr = _to_c_arr(closes)
        res = _DarvasResult()
        _lib.darvas_classify(h_ptr, l_ptr, c_ptr, n, confirm, lookback,
                             ctypes.byref(res))
        return {
            "signal":              _SIGNAL_MAP.get(res.signal, "UNKNOWN"),
            "box_top":             round(res.box_top, 2)             if res.box_top     else None,
            "box_bottom":          round(res.box_bottom, 2)          if res.box_bottom  else None,
            "current_price":       round(res.current_price, 2),
            "upside_to_top_pct":   round(res.upside_to_top_pct, 2),
            "position_in_box_pct": round(res.position_in_box_pct, 1),
            "data_points":         res.data_points,
            "engine":              "C",
        }
    else:
        # Python fallback — same algorithm
        from full_indian_market_scan import compute_darvas_box
        result = compute_darvas_box(df, confirm=confirm)
        result["engine"] = "Python"
        return result


def darvas_walk_forward_fast(df: pd.DataFrame,
                              confirm: int = 3, cooldown: int = 10,
                              vol_threshold: float = 1.2) -> list:
    """
    Walk-forward Darvas breakout signal detection for full OHLC history.
    Uses C implementation if available (100× faster than Python for large datasets).

    vol_threshold: volume must be ≥ this × 20-bar average (0 = disable).

    Returns list of dicts: [{signal_date, entry_price, box_top, box_bottom}, ...]
    """
    if df is None or df.empty or len(df) < confirm + 25:
        return []

    highs  = df["High"].values.astype(np.float64)
    lows   = df["Low"].values.astype(np.float64)
    closes = df["Close"].values.astype(np.float64)
    vols   = df["Volume"].values.astype(np.float64) \
             if "Volume" in df.columns else None
    n      = len(closes)

    if _C_AVAILABLE:
        max_sigs  = n // 5 + 10   # generous upper bound
        sig_array = (_DarvasSignal * max_sigs)()
        h_ptr, h_arr = _to_c_arr(highs)
        l_ptr, l_arr = _to_c_arr(lows)
        c_ptr, c_arr = _to_c_arr(closes)
        if vols is not None:
            v_ptr, v_arr = _to_c_arr(vols)
        else:
            v_ptr = None
        n_found = _lib.darvas_walk_forward(
            h_ptr, l_ptr, c_ptr, v_ptr, n,
            confirm, cooldown, vol_threshold,
            sig_array, max_sigs
        )
        return [
            {
                "date":        df.index[sig_array[i].bar_idx],
                "entry_price": round(sig_array[i].entry_price, 2),
                "box_top":     round(sig_array[i].box_top, 2),
                "box_bottom":  round(sig_array[i].box_bottom, 2),
                "signal_idx":  sig_array[i].bar_idx,
                "engine":      "C",
            }
            for i in range(n_found)
        ]
    else:
        # Python fallback
        from backtest_screeners import detect_darvas_signals
        return detect_darvas_signals(df, confirm=confirm, cooldown=cooldown)


def zscore_window_fast(window: np.ndarray) -> np.ndarray:
    """
    Z-score normalise a (rows × cols) feature window in-place using C.
    Equivalent to ml_signal_engine.z_score_normalise() but via C.
    """
    if not _C_AVAILABLE:
        from ml_signal_engine import z_score_normalise
        return z_score_normalise(window)
    arr  = np.ascontiguousarray(window, dtype=np.float64)
    rows, cols = arr.shape
    ptr  = arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    _lib.zscore_normalize_window(ptr, rows, cols)
    return arr


def benchmark(df: pd.DataFrame, n_reps: int = 100) -> dict:
    """
    Benchmark C vs Python Darvas for one stock.
    Returns timing dict for comparison.
    """
    import time

    # Python
    t0 = time.perf_counter()
    for _ in range(n_reps):
        from full_indian_market_scan import compute_darvas_box
        compute_darvas_box(df)
    t_py = (time.perf_counter() - t0) / n_reps * 1000

    # C
    t0 = time.perf_counter()
    for _ in range(n_reps):
        darvas_classify_fast(df)
    t_c = (time.perf_counter() - t0) / n_reps * 1000

    speedup = t_py / t_c if t_c > 0 else float("inf")
    print(f"  Python: {t_py:.3f}ms/call | C: {t_c:.3f}ms/call | Speedup: {speedup:.0f}×")
    return {"python_ms": t_py, "c_ms": t_c, "speedup": speedup,
            "c_available": _C_AVAILABLE}
