/*
 * darvas_fast.c — High-performance Darvas Box signal detector
 * ============================================================
 * C implementation of the walk-forward Darvas Box algorithm.
 * Compiled as a shared library and called from Python via ctypes.
 *
 * Performance target: 100× faster than pure Python for the inner loops.
 * Profiling showed Python Darvas takes 13ms for 10 stocks (2,490 bars).
 * For full NSE (2,400 stocks × 1,258 bars = 3M bar-iterations), C reduces
 * this from ~3s → ~30ms, making data collection the clear bottleneck.
 *
 * Compile:
 *   gcc -O3 -march=native -shared -fPIC -o darvas_fast.so darvas_fast.c
 *
 * The -O3 flag enables:
 *   - Vectorisation (SIMD) for the inner comparison loops
 *   - Loop unrolling
 *   - Inlining of small functions
 *   - Branch prediction hints
 */

#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Signal codes returned to Python */
#define SIG_NO_BOX         0
#define SIG_IN_BOX         1
#define SIG_BREAKOUT_BUY   2
#define SIG_BREAKDOWN_SELL 3
#define SIG_INSUFFICIENT   4

/* Result struct (matches Python dict keys) */
typedef struct {
    int    signal;
    double box_top;
    double box_bottom;
    double current_price;
    double upside_to_top_pct;
    double position_in_box_pct;
    int    data_points;
} DarvasResult;

/* Signal struct for walk-forward scan */
typedef struct {
    int    bar_idx;
    double entry_price;
    double box_top;
    double box_bottom;
} DarvasSignal;

/*
 * darvas_classify — classify current bar relative to the Darvas Box.
 *
 * This replicates detect_darvas_signals() from full_indian_market_scan.py
 * but in C, with the same design invariant:
 *   CURRENT bar is excluded from box formation.
 *   Box formed from bars [0, n-1), classified against bar n-1.
 *
 * Args:
 *   highs     : array of daily high prices (length n)
 *   lows      : array of daily low prices  (length n)
 *   closes    : array of closing prices    (length n)
 *   n         : number of bars
 *   confirm   : confirmation days (default 3)
 *   lookback  : how far back to search for box top (default 60)
 *   result    : output struct (caller allocates)
 */
void darvas_classify(const double *highs, const double *lows,
                     const double *closes, int n, int confirm, int lookback,
                     DarvasResult *result) {

    result->signal          = SIG_INSUFFICIENT;
    result->box_top         = 0.0;
    result->box_bottom      = 0.0;
    result->current_price   = n > 0 ? closes[n-1] : 0.0;
    result->data_points     = n;

    if (n < confirm + 5) return;

    double current = closes[n - 1];
    int    nh      = n - 1;          /* historical bars: 0..n-2 */

    /* --- Step 1: Find most recent confirmed box top ------------------------ */
    int    box_top_idx = -1;
    double box_top     = 0.0;
    int    search_from = (nh - lookback > 0) ? nh - lookback : 0;

    for (int j = nh - confirm - 1; j >= search_from; j--) {
        if (highs[j] == 0.0) continue;
        /* Check: next `confirm` bars all have lower highs */
        int confirmed = 1;
        for (int k = j + 1; k <= j + confirm && k < nh; k++) {
            if (highs[k] >= highs[j]) { confirmed = 0; break; }
        }
        if (confirmed && (j + confirm) < nh) {
            box_top     = highs[j];
            box_top_idx = j;
            break;
        }
    }

    if (box_top_idx < 0) {
        result->signal = SIG_NO_BOX;
        return;
    }

    /* --- Step 2: Find confirmed box bottom --------------------------------- */
    double box_bottom = 0.0;
    int    seg_len    = nh - box_top_idx;

    for (int j = box_top_idx; j < nh - confirm; j++) {
        if (lows[j] == 0.0) continue;
        int confirmed = 1;
        for (int k = j + 1; k <= j + confirm && k < nh; k++) {
            if (lows[k] <= lows[j]) { confirmed = 0; break; }
        }
        if (confirmed) {
            box_bottom = lows[j];
            break;
        }
    }

    /* Fallback: minimum low in the segment */
    if (box_bottom == 0.0) {
        double min_low = 1e18;
        for (int j = box_top_idx; j < nh; j++) {
            if (lows[j] > 0.0 && lows[j] < min_low)
                min_low = lows[j];
        }
        box_bottom = (min_low < 1e18) ? min_low : 0.0;
    }

    if (box_bottom == 0.0) {
        result->signal  = SIG_NO_BOX;
        result->box_top = box_top;
        return;
    }

    /* --- Step 3: Classify current bar ------------------------------------- */
    int signal;
    if      (current > box_top)    signal = SIG_BREAKOUT_BUY;
    else if (current < box_bottom) signal = SIG_BREAKDOWN_SELL;
    else                           signal = SIG_IN_BOX;

    double box_range = box_top - box_bottom;
    double upside    = (box_range > 0 && current > 0) ?
                       (box_top - current) / current * 100.0 : 0.0;
    double pos_pct   = (box_range > 0) ?
                       (current - box_bottom) / box_range * 100.0 : 0.0;

    result->signal              = signal;
    result->box_top             = box_top;
    result->box_bottom          = box_bottom;
    result->current_price       = current;
    result->upside_to_top_pct   = upside;
    result->position_in_box_pct = pos_pct;
}

/*
 * darvas_walk_forward — scan all bars for breakout signals (walk-forward).
 *
 * For each bar i from (confirm+20) to (n-1):
 *   Use only bars [0..i-1] for box formation (no lookahead).
 *   If breakout detected and cooldown respected, emit a signal.
 *
 * Returns number of signals found. Signals written to out_signals[].
 * Caller must allocate out_signals with max_signals capacity.
 */
int darvas_walk_forward(const double *highs, const double *lows,
                        const double *closes, const double *volumes,
                        int n, int confirm, int cooldown,
                        double vol_threshold,
                        DarvasSignal *out_signals, int max_signals) {
    int    n_found   = 0;
    int    last_sig  = -(cooldown + 1);

    for (int i = confirm + 20; i < n && n_found < max_signals; i++) {
        /* Build temporary view of bars [0..i-1] */
        int    nh     = i;
        int    search = (nh - 60 > 0) ? nh - 60 : 0;

        /* Find box top */
        int    bti = -1;
        double bt  = 0.0;
        for (int j = nh - confirm - 1; j >= search; j--) {
            if (highs[j] == 0.0) continue;
            int ok = 1;
            for (int k = j+1; k <= j+confirm && k < nh; k++)
                if (highs[k] >= highs[j]) { ok = 0; break; }
            if (ok && (j + confirm) < nh) { bt = highs[j]; bti = j; break; }
        }
        if (bti < 0) continue;

        /* Check breakout: first close above box top */
        double curr = closes[i];
        double prev = closes[i - 1];
        if (!(curr > bt && prev <= bt)) continue;
        if ((i - last_sig) < cooldown) continue;

        /* Volume confirmation */
        if (vol_threshold > 0.0 && i >= 20 && volumes != NULL) {
            double avg_vol = 0.0;
            for (int k = i - 20; k < i; k++) avg_vol += volumes[k];
            avg_vol /= 20.0;
            if (volumes[i] < avg_vol * vol_threshold) continue;
        }

        out_signals[n_found].bar_idx     = i;
        out_signals[n_found].entry_price = curr;
        out_signals[n_found].box_top     = bt;
        /* Approximate box bottom as min low from bti onwards */
        double min_l = 1e18;
        for (int k = bti; k < i; k++)
            if (lows[k] > 0.0 && lows[k] < min_l) min_l = lows[k];
        out_signals[n_found].box_bottom = (min_l < 1e18) ? min_l : 0.0;
        n_found++;
        last_sig = i;
    }
    return n_found;
}

/*
 * zscore_normalize_window — Z-score normalise a (lookback × n_features) matrix.
 * Used by ML signal engine to normalise the 60-day sliding window.
 * Operates in-place on the flat array (row-major).
 */
void zscore_normalize_window(double *data, int rows, int cols) {
    for (int c = 0; c < cols; c++) {
        double sum = 0.0, sum_sq = 0.0;
        for (int r = 0; r < rows; r++) sum    += data[r * cols + c];
        double mean = sum / rows;
        for (int r = 0; r < rows; r++) {
            double d = data[r * cols + c] - mean;
            sum_sq  += d * d;
        }
        double std = (sum_sq > 0) ? sqrt(sum_sq / rows) : 1.0;
        for (int r = 0; r < rows; r++)
            data[r * cols + c] = (data[r * cols + c] - mean) / std;
    }
}
