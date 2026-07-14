#!/usr/bin/env Rscript
# =============================================================
#  Pegu Score & Sarvas Scan — NSE / BSE Equity Analysis
# =============================================================
#
#  Pegu Score  : Composite fundamental score (0–100)
#                Weights: Valuation 30 | Quality 30 | Growth 25 | Safety 15
#
#  Sarvas Scan : Sanskrit "sarvas" = complete/whole.
#                Multi-criteria screen blending technicals + fundamentals.
#                Produces a Sarvas Score (0–100) and BUY/SELL signal.
#
#  Inputs  (from nse_bse_extractor.py, via data/market_data.duckdb):
#    all_stocks_combined table       — preferred
#    nse_stocks_fundamental  +  bse_stocks_fundamental tables
#
#  Outputs (→ reports/):
#    pegu_sarvas_all_stocks.csv   — full scored universe
#    sarvas_scan_results.csv      — stocks passing strict Sarvas filter
#    top_pegu_picks.csv           — top-N by Pegu score
#    pegu_sarvas_NSE.csv          — NSE-only results
#    pegu_sarvas_BSE.csv          — BSE-only results
#    sector_pegu_analysis.csv     — sector-level aggregation
#    pegu_score_distribution.png  — histogram
#    pegu_vs_sarvas.png           — scatter
#    top20_pegu.png               — bar chart
#    sector_pegu_heatmap.png      — grade heatmap
#
#  Usage:
#    Rscript pegu_sarvas_analysis.R
#    Rscript pegu_sarvas_analysis.R --data-dir data --top-n 50
# =============================================================

suppressPackageStartupMessages({
  library(dplyr)
  library(ggplot2)
  library(tidyr)
  library(readr)
  library(scales)
  library(duckdb)
  library(DBI)
})

# ── CLI arguments ─────────────────────────────────────────────
argv       <- commandArgs(trailingOnly = TRUE)
data_dir   <- if ("--data-dir" %in% argv) argv[which(argv == "--data-dir") + 1] else "data"
output_dir <- if ("--out-dir"  %in% argv) argv[which(argv == "--out-dir")  + 1] else "reports"
top_n      <- if ("--top-n"    %in% argv) as.integer(argv[which(argv == "--top-n") + 1]) else 50L

dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

cat("=============================================================\n")
cat("  Pegu Score & Sarvas Scan Analysis\n")
cat(sprintf("  Data    : %s\n", data_dir))
cat(sprintf("  Reports : %s\n", output_dir))
cat(sprintf("  Top-N   : %d\n", top_n))
cat("=============================================================\n\n")


# ─────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────
load_data <- function(data_dir) {
  db_path <- file.path(data_dir, "market_data.duckdb")
  if (!file.exists(db_path)) stop("No market_data.duckdb found in: ", data_dir)
  con <- dbConnect(duckdb(), db_path, read_only = TRUE)
  on.exit(dbDisconnect(con, shutdown = TRUE))

  if ("all_stocks_combined" %in% dbListTables(con)) {
    cat(sprintf("[LOAD] %s :: all_stocks_combined\n", db_path))
    return(dbReadTable(con, "all_stocks_combined"))
  }
  parts <- lapply(c("nse", "bse"), function(x) {
    table <- sprintf("%s_stocks_fundamental", x)
    if (table %in% dbListTables(con)) {
      cat(sprintf("[LOAD] %s :: %s\n", db_path, table))
      dbReadTable(con, table)
    } else NULL
  })
  parts <- Filter(Negate(is.null), parts)
  if (length(parts) == 0) stop("No fundamental tables found in: ", db_path)
  bind_rows(parts)
}

df_raw <- load_data(data_dir)
cat(sprintf("[INFO] %d rows loaded from %d exchange(s)\n\n",
            nrow(df_raw), n_distinct(df_raw$exchange)))


# ─────────────────────────────────────────────────────────────
# 2. CLEAN & NORMALISE
# ─────────────────────────────────────────────────────────────
pct_fix <- function(x) {
  # yfinance returns some ratios as decimals (0.15 = 15%), others as plain %
  ifelse(!is.na(x) & abs(x) < 2, x * 100, x)
}

clean_data <- function(df) {
  df %>%
    # Keep one row per symbol (prefer NSE over BSE)
    arrange(symbol, desc(exchange == "NSE")) %>%
    distinct(symbol, .keep_all = TRUE) %>%
    filter(!is.na(last_price), last_price > 0) %>%
    mutate(
      # Convert decimal-form ratios to percentage
      roe_pct             = pct_fix(roe),
      roa_pct             = pct_fix(roa),
      gross_margins_pct   = pct_fix(gross_margins),
      operating_margins_pct = pct_fix(operating_margins),
      profit_margins_pct  = pct_fix(profit_margins),
      revenue_growth_pct  = pct_fix(revenue_growth),
      earnings_growth_pct = pct_fix(earnings_growth),
      dividend_yield_pct  = pct_fix(dividend_yield),
      # Clamp unrealistic outliers
      pe_ratio    = if_else(!is.na(pe_ratio)    & pe_ratio    > 0 & pe_ratio    < 1000, pe_ratio,    NA_real_),
      pb_ratio    = if_else(!is.na(pb_ratio)    & pb_ratio    > 0 & pb_ratio    < 200,  pb_ratio,    NA_real_),
      peg_ratio   = if_else(!is.na(peg_ratio)   & peg_ratio   > 0 & peg_ratio   < 100,  peg_ratio,   NA_real_),
      ev_ebitda   = if_else(!is.na(ev_ebitda)   & ev_ebitda   > 0 & ev_ebitda   < 500,  ev_ebitda,   NA_real_),
      debt_equity = if_else(!is.na(debt_equity) & debt_equity >= 0 & debt_equity < 1000, debt_equity, NA_real_),
      beta        = if_else(!is.na(beta)        & abs(beta) < 10,  beta,        NA_real_)
    )
}

df <- clean_data(df_raw)
cat(sprintf("[INFO] After cleaning: %d valid stocks\n\n", nrow(df)))


# ─────────────────────────────────────────────────────────────
# 3. PEGU SCORE  (0–100)
# ─────────────────────────────────────────────────────────────
#   Valuation   30 pts  (P/E 10 + PEG 10 + P/B 10)
#   Quality     30 pts  (ROE 10 + Oper. Margin 10 + D/E 10)
#   Growth      25 pts  (EPS growth 10 + Rev growth 10 + Fwd PE 5)
#   Safety      15 pts  (Current ratio 5 + Div yield 5 + Beta 5)
# ─────────────────────────────────────────────────────────────
pegu_score <- function(df) {
  df %>% mutate(

    # ── VALUATION (max 30) ─────────────────────────────────
    pe_score = case_when(
      is.na(pe_ratio) | pe_ratio <= 0 ~ 3L,
      pe_ratio <  8   ~ 10L,
      pe_ratio < 12   ~  9L,
      pe_ratio < 16   ~  7L,
      pe_ratio < 22   ~  5L,
      pe_ratio < 30   ~  3L,
      pe_ratio < 50   ~  1L,
      TRUE            ~  0L
    ),
    peg_score = case_when(
      is.na(peg_ratio)           ~  4L,
      peg_ratio <= 0             ~  0L,
      peg_ratio <  0.5           ~ 10L,
      peg_ratio <  1.0           ~  8L,
      peg_ratio <  1.5           ~  5L,
      peg_ratio <  2.0           ~  2L,
      TRUE                       ~  0L
    ),
    pb_score = case_when(
      is.na(pb_ratio) | pb_ratio <= 0 ~ 3L,
      pb_ratio <  1   ~ 10L,
      pb_ratio <  2   ~  8L,
      pb_ratio <  3   ~  6L,
      pb_ratio <  5   ~  4L,
      pb_ratio < 10   ~  2L,
      TRUE            ~  0L
    ),
    valuation_score = pe_score + peg_score + pb_score,     # 0–30

    # ── QUALITY (max 30) ───────────────────────────────────
    roe_score = case_when(
      is.na(roe_pct)  ~  3L,
      roe_pct > 35    ~ 10L,
      roe_pct > 25    ~  9L,
      roe_pct > 20    ~  7L,
      roe_pct > 15    ~  5L,
      roe_pct > 10    ~  3L,
      roe_pct >  0    ~  1L,
      TRUE            ~  0L
    ),
    margin_score = case_when(
      is.na(operating_margins_pct) ~  3L,
      operating_margins_pct > 35   ~ 10L,
      operating_margins_pct > 25   ~  8L,
      operating_margins_pct > 18   ~  6L,
      operating_margins_pct > 12   ~  4L,
      operating_margins_pct >  6   ~  2L,
      operating_margins_pct >  0   ~  1L,
      TRUE                         ~  0L
    ),
    debt_score = case_when(
      is.na(debt_equity) ~  4L,
      debt_equity == 0   ~ 10L,
      debt_equity <  0.1 ~  9L,
      debt_equity <  0.3 ~  8L,
      debt_equity <  0.5 ~  7L,
      debt_equity <  1.0 ~  5L,
      debt_equity <  1.5 ~  3L,
      debt_equity <  2.5 ~  1L,
      TRUE               ~  0L
    ),
    quality_score = roe_score + margin_score + debt_score,  # 0–30

    # ── GROWTH (max 25) ────────────────────────────────────
    eps_growth_score = case_when(
      is.na(earnings_growth_pct) ~  3L,
      earnings_growth_pct > 40   ~ 10L,
      earnings_growth_pct > 25   ~  8L,
      earnings_growth_pct > 15   ~  6L,
      earnings_growth_pct >  8   ~  4L,
      earnings_growth_pct >  0   ~  2L,
      TRUE                       ~  0L
    ),
    rev_growth_score = case_when(
      is.na(revenue_growth_pct) ~  3L,
      revenue_growth_pct > 30   ~ 10L,
      revenue_growth_pct > 20   ~  8L,
      revenue_growth_pct > 12   ~  6L,
      revenue_growth_pct >  6   ~  4L,
      revenue_growth_pct >  0   ~  2L,
      TRUE                      ~  0L
    ),
    forward_pe_score = case_when(
      is.na(forward_pe) | is.na(pe_ratio) | pe_ratio <= 0 ~ 2L,
      forward_pe < pe_ratio * 0.65                         ~ 5L,
      forward_pe < pe_ratio * 0.80                         ~ 4L,
      forward_pe < pe_ratio * 0.95                         ~ 3L,
      forward_pe < pe_ratio                                ~ 2L,
      TRUE                                                  ~ 0L
    ),
    growth_score = eps_growth_score + rev_growth_score + forward_pe_score,  # 0–25

    # ── SAFETY (max 15) ────────────────────────────────────
    curr_ratio_score = case_when(
      is.na(current_ratio)                                    ~ 2L,
      current_ratio >= 2.0 & current_ratio <= 4.0             ~ 5L,
      current_ratio >= 1.5 & current_ratio <  2.0             ~ 4L,
      current_ratio >= 1.2 & current_ratio <  1.5             ~ 3L,
      current_ratio >= 1.0 & current_ratio <  1.2             ~ 2L,
      TRUE                                                     ~ 0L
    ),
    dividend_score = case_when(
      is.na(dividend_yield_pct) | dividend_yield_pct <= 0 ~ 0L,
      dividend_yield_pct >= 5                              ~ 5L,
      dividend_yield_pct >= 3                              ~ 4L,
      dividend_yield_pct >= 2                              ~ 3L,
      dividend_yield_pct >= 1                              ~ 2L,
      TRUE                                                 ~ 1L
    ),
    beta_score = case_when(
      is.na(beta)                        ~ 2L,
      beta >= 0.6 & beta <= 1.2          ~ 5L,
      beta >= 0.4 & beta <  0.6          ~ 4L,
      beta >  1.2 & beta <= 1.5          ~ 3L,
      beta >  1.5 & beta <= 2.0          ~ 2L,
      beta >  2.0                         ~ 1L,
      TRUE                               ~ 2L
    ),
    safety_score = curr_ratio_score + dividend_score + beta_score,  # 0–15

    # ── TOTAL ──────────────────────────────────────────────
    pegu_score = valuation_score + quality_score + growth_score + safety_score,

    pegu_grade = case_when(
      pegu_score >= 80 ~ "A+ Excellent",
      pegu_score >= 70 ~ "A  Very Good",
      pegu_score >= 60 ~ "B+ Good",
      pegu_score >= 50 ~ "B  Average",
      pegu_score >= 40 ~ "C  Below Avg",
      pegu_score >= 25 ~ "D  Weak",
      TRUE             ~ "F  Poor"
    ),

    pegu_percentile = round(percent_rank(pegu_score) * 100, 1)
  )
}

cat("[INFO] Calculating Pegu scores...\n")
df_p <- pegu_score(df)
cat(sprintf("[INFO] Score range: [%d, %d]  mean=%.1f  median=%.1f\n\n",
            min(df_p$pegu_score, na.rm = TRUE),
            max(df_p$pegu_score, na.rm = TRUE),
            mean(df_p$pegu_score, na.rm = TRUE),
            median(df_p$pegu_score, na.rm = TRUE)))


# ─────────────────────────────────────────────────────────────
# 4. SARVAS SCAN  (0–100)
# ─────────────────────────────────────────────────────────────
sarvas_scan <- function(df) {
  df %>% mutate(

    # ── Technical signals ──────────────────────────────────
    above_50dma    = if_else(!is.na(ma_50)  & ma_50  > 0, last_price > ma_50,  NA),
    above_200dma   = if_else(!is.na(ma_200) & ma_200 > 0, last_price > ma_200, NA),
    golden_cross   = if_else(!is.na(ma_50)  & !is.na(ma_200), ma_50 > ma_200, NA),
    rsi_neutral    = if_else(!is.na(rsi_14), rsi_14 >= 35 & rsi_14 <= 68, NA),
    rsi_oversold   = if_else(!is.na(rsi_14), rsi_14 <  35, NA),
    rsi_overbought = if_else(!is.na(rsi_14), rsi_14 >  70, NA),
    macd_bullish   = if_else(!is.na(macd) & !is.na(macd_signal), macd > macd_signal, NA),
    vol_surge      = if_else(!is.na(volume_ratio), volume_ratio > 1.5, NA),
    near_52w_high  = if_else(!is.na(w52_high) & w52_high > 0, (last_price / w52_high) >= 0.80, NA),

    # ── Fundamental signals ────────────────────────────────
    positive_eps   = !is.na(eps_trailing) & eps_trailing > 0,
    eps_growing    = !is.na(earnings_growth_pct) & earnings_growth_pct > 10,
    rev_growing    = !is.na(revenue_growth_pct)  & revenue_growth_pct  >  8,
    reasonable_pe  = !is.na(pe_ratio) & pe_ratio > 0 & pe_ratio < 35,
    low_debt       = !is.na(debt_equity) & debt_equity < 1,
    strong_roe     = !is.na(roe_pct)    & roe_pct > 15,
    analyst_upside = !is.na(upside_pct) & upside_pct > 10,
    strong_pegu    = pegu_score >= 60,
    good_pegu      = pegu_score >= 50,

    # ── Sarvas Score  (max ~100) ───────────────────────────
    #   Technical  45 pts  |  Fundamental  55 pts
    sarvas_score = (
      coalesce(as.integer(above_50dma),   0L) * 10L +
      coalesce(as.integer(above_200dma),  0L) * 10L +
      coalesce(as.integer(golden_cross),  0L) *  8L +
      coalesce(as.integer(rsi_neutral),   0L) *  7L +
      coalesce(as.integer(macd_bullish),  0L) *  5L +
      coalesce(as.integer(vol_surge),     0L) *  3L +
      coalesce(as.integer(near_52w_high), 0L) *  2L +
      as.integer(positive_eps)   *  8L +
      as.integer(eps_growing)    *  7L +
      as.integer(rev_growing)    *  6L +
      as.integer(reasonable_pe)  *  5L +
      as.integer(low_debt)       *  5L +
      as.integer(strong_roe)     *  5L +
      as.integer(analyst_upside) *  4L +
      # Pegu bonus: up to 15 pts scaled from score 40–100
      pmin(15L, pmax(0L, as.integer((pegu_score - 40L) * 15L / 60L)))
    ),
    sarvas_score = pmin(100L, pmax(0L, sarvas_score)),

    # ── Sarvas Signal ──────────────────────────────────────
    sarvas_signal = case_when(
      sarvas_score >= 80 ~ "STRONG BUY",
      sarvas_score >= 65 ~ "BUY",
      sarvas_score >= 50 ~ "ACCUMULATE",
      sarvas_score >= 35 ~ "HOLD",
      sarvas_score >= 20 ~ "REDUCE",
      TRUE               ~ "SELL"
    ),

    # ── Strict pass: must satisfy all key criteria ─────────
    sarvas_pass = (
      coalesce(above_50dma,  FALSE) &
      coalesce(above_200dma, FALSE) &
      coalesce(rsi_neutral,  FALSE) &
      strong_pegu                   &
      positive_eps                  &
      reasonable_pe
    )
  )
}

cat("[INFO] Running Sarvas scan...\n")
df_f <- sarvas_scan(df_p)
n_pass <- sum(df_f$sarvas_pass, na.rm = TRUE)
n_buy  <- sum(df_f$sarvas_signal %in% c("STRONG BUY", "BUY"), na.rm = TRUE)
cat(sprintf("[INFO] Sarvas: %d strict-pass | %d BUY/STRONG BUY signals\n\n",
            n_pass, n_buy))


# ─────────────────────────────────────────────────────────────
# 5. SAVE OUTPUTS
# ─────────────────────────────────────────────────────────────
OUTPUT_COLS <- c(
  "symbol", "exchange", "company_name", "sector", "industry",
  "last_price", "market_cap",
  "pe_ratio", "pb_ratio", "peg_ratio", "ev_ebitda",
  "roe_pct", "roa_pct", "operating_margins_pct", "profit_margins_pct",
  "debt_equity", "current_ratio",
  "revenue_growth_pct", "earnings_growth_pct",
  "eps_trailing", "eps_forward",
  "dividend_yield_pct", "beta",
  "ma_50", "ma_200", "rsi_14", "macd", "macd_signal", "volume_ratio",
  "return_1w_pct", "return_1m_pct", "return_3m_pct", "return_6m_pct", "return_1y_pct",
  "w52_high", "w52_low", "target_price", "upside_pct",
  "analyst_recommendation",
  "pe_score", "peg_score", "pb_score",       "valuation_score",
  "roe_score", "margin_score", "debt_score",  "quality_score",
  "eps_growth_score", "rev_growth_score", "forward_pe_score", "growth_score",
  "curr_ratio_score", "dividend_score", "beta_score",         "safety_score",
  "pegu_score", "pegu_grade", "pegu_percentile",
  "above_50dma", "above_200dma", "golden_cross", "rsi_neutral",
  "macd_bullish", "vol_surge", "near_52w_high",
  "positive_eps", "eps_growing", "strong_roe", "analyst_upside",
  "sarvas_score", "sarvas_signal", "sarvas_pass"
)

avail <- intersect(OUTPUT_COLS, names(df_f))
df_out <- df_f %>%
  select(all_of(avail)) %>%
  arrange(desc(pegu_score), desc(sarvas_score))

save_csv <- function(df, filename) {
  path <- file.path(output_dir, filename)
  write_csv(df, path)
  cat(sprintf("[SAVE] %-55s (%d rows)\n", filename, nrow(df)))
}

save_csv(df_out, "pegu_sarvas_all_stocks.csv")

# Sarvas strict-pass
df_pass <- df_out %>% filter(sarvas_pass == TRUE) %>%
  arrange(desc(sarvas_score), desc(pegu_score))
save_csv(df_pass, "sarvas_scan_results.csv")

# Top-N by Pegu
df_top <- df_out %>%
  filter(is.na(positive_eps) | positive_eps == TRUE) %>%
  arrange(desc(pegu_score)) %>% head(top_n)
save_csv(df_top, "top_pegu_picks.csv")

# Per-exchange files
for (exc in unique(df_out$exchange)) {
  save_csv(filter(df_out, exchange == exc) %>% arrange(desc(pegu_score)),
           sprintf("pegu_sarvas_%s.csv", tolower(exc)))
}

# Sector summary
if ("sector" %in% names(df_out)) {
  df_sect <- df_f %>%
    filter(!is.na(sector), sector != "") %>%
    group_by(sector, exchange) %>%
    summarise(
      n_stocks       = n(),
      avg_pegu       = round(mean(pegu_score, na.rm = TRUE), 1),
      median_pegu    = round(median(pegu_score, na.rm = TRUE), 1),
      avg_sarvas     = round(mean(sarvas_score, na.rm = TRUE), 1),
      n_buy          = sum(sarvas_signal %in% c("STRONG BUY", "BUY"), na.rm = TRUE),
      n_sarvas_pass  = sum(sarvas_pass, na.rm = TRUE),
      avg_pe         = round(mean(pe_ratio, na.rm = TRUE), 1),
      avg_roe        = round(mean(roe_pct, na.rm = TRUE), 1),
      avg_rev_growth = round(mean(revenue_growth_pct, na.rm = TRUE), 1),
      .groups = "drop"
    ) %>% arrange(desc(avg_pegu))
  save_csv(df_sect, "sector_pegu_analysis.csv")
}
cat("\n")


# ─────────────────────────────────────────────────────────────
# 6. VISUALISATIONS
# ─────────────────────────────────────────────────────────────
make_plots <- function(df, df_f, output_dir) {

  # helper: safe ggsave
  sg <- function(p, name, w = 10, h = 6) {
    tryCatch(
      ggsave(file.path(output_dir, name), p, width = w, height = h, dpi = 150),
      error = function(e) cat("[WARN] Plot failed:", name, "-", conditionMessage(e), "\n")
    )
  }

  # ── 1: Pegu score distribution ───────────────────────────
  p1 <- ggplot(df, aes(x = pegu_score, fill = exchange)) +
    geom_histogram(bins = 26, color = "white", alpha = 0.80, position = "stack") +
    scale_fill_manual(values = c("NSE" = "#1f77b4", "BSE" = "#ff7f0e")) +
    geom_vline(xintercept = c(50, 60, 70), linetype = "dashed",
               colour = c("#888", "#555", "#222")) +
    annotate("text", x = c(51, 61, 71), y = Inf,
             label = c("B=50", "B+=60", "A=70"),
             angle = 90, vjust = 1.4, hjust = 1.1, size = 3) +
    labs(
      title    = "Pegu Score Distribution — NSE & BSE",
      subtitle = sprintf("n=%d | mean=%.1f | median=%.1f",
                         nrow(df), mean(df$pegu_score), median(df$pegu_score)),
      x = "Pegu Score (0–100)", y = "Count", fill = "Exchange"
    ) +
    theme_minimal(base_size = 12) + theme(legend.position = "top")
  sg(p1, "pegu_score_distribution.png")

  # ── 2: Pegu vs Sarvas scatter ─────────────────────────────
  p2 <- df %>%
    filter(!is.na(pegu_score), !is.na(sarvas_score)) %>%
    ggplot(aes(x = pegu_score, y = sarvas_score, colour = sarvas_signal)) +
    geom_point(size = 1.4, alpha = 0.65) +
    scale_colour_manual(values = c(
      "STRONG BUY" = "#006400", "BUY"        = "#228B22",
      "ACCUMULATE" = "#7EB07E", "HOLD"        = "#FFA500",
      "REDUCE"     = "#FF6347", "SELL"        = "#DC143C"
    )) +
    geom_hline(yintercept = 65, linetype = "dashed", colour = "#228B22", alpha = 0.6) +
    geom_vline(xintercept = 60, linetype = "dashed", colour = "#1f77b4", alpha = 0.6) +
    labs(
      title    = "Pegu Score vs Sarvas Score",
      subtitle = "Top-right quadrant = best stocks (strong fundamentals + positive technicals)",
      x = "Pegu Score (0–100, Fundamentals)",
      y = "Sarvas Score (0–100, Technical + Fundamental)",
      colour = "Signal"
    ) +
    theme_minimal(base_size = 12)
  sg(p2, "pegu_vs_sarvas.png", w = 10, h = 7)

  # ── 3: Top-20 bar chart ───────────────────────────────────
  top20 <- df %>%
    arrange(desc(pegu_score)) %>% head(20) %>%
    mutate(lbl = paste0(symbol, "\n(", exchange, ")"))

  p3 <- ggplot(top20, aes(x = reorder(lbl, pegu_score), y = pegu_score,
                           fill = pegu_grade)) +
    geom_col(alpha = 0.85) +
    geom_text(aes(label = pegu_score), hjust = -0.15, size = 3.5) +
    coord_flip() +
    scale_fill_brewer(palette = "RdYlGn", direction = 1) +
    expand_limits(y = 110) +
    labs(
      title = "Top 20 Stocks by Pegu Score",
      x = NULL, y = "Pegu Score (0–100)", fill = "Grade"
    ) +
    theme_minimal(base_size = 12)
  sg(p3, "top20_pegu.png", w = 10, h = 8)

  # ── 4: Sector grade heatmap ───────────────────────────────
  if ("sector" %in% names(df) && any(!is.na(df$sector))) {
    heat <- df %>%
      filter(!is.na(sector), sector != "", !is.na(pegu_grade)) %>%
      count(sector, pegu_grade) %>%
      group_by(sector) %>%
      mutate(pct = n / sum(n) * 100) %>%
      ungroup()

    if (nrow(heat) > 0) {
      p4 <- ggplot(heat, aes(x = pegu_grade, y = reorder(sector, pct), fill = pct)) +
        geom_tile(colour = "white", linewidth = 0.4) +
        geom_text(aes(label = sprintf("%.0f%%", pct)), size = 2.8) +
        scale_fill_gradient2(low = "#f7fbff", mid = "#6baed6",
                             high = "#08306b", midpoint = 30) +
        labs(
          title = "Pegu Grade Distribution by Sector",
          x = "Pegu Grade", y = NULL, fill = "% of Stocks"
        ) +
        theme_minimal(base_size = 11) +
        theme(axis.text.x = element_text(angle = 35, hjust = 1))
      sg(p4, "sector_pegu_heatmap.png", w = 12, h = 8)
    }
  }

  # ── 5: Score component breakdown for top stocks ───────────
  comp_cols <- c("symbol", "valuation_score", "quality_score",
                 "growth_score", "safety_score", "pegu_score")
  avail_comp <- intersect(comp_cols, names(df))
  if (length(avail_comp) == length(comp_cols)) {
    radar_data <- df %>%
      arrange(desc(pegu_score)) %>% head(15) %>%
      select(all_of(comp_cols)) %>%
      pivot_longer(-c(symbol, pegu_score),
                   names_to = "component", values_to = "score") %>%
      mutate(component = sub("_score$", "", component))

    p5 <- ggplot(radar_data,
                 aes(x = reorder(symbol, -pegu_score), y = score,
                     fill = component)) +
      geom_col(position = "stack", alpha = 0.85) +
      scale_fill_brewer(palette = "Set2") +
      labs(
        title = "Pegu Score Components — Top 15 Stocks",
        x = NULL, y = "Component Score", fill = "Component"
      ) +
      theme_minimal(base_size = 11) +
      theme(axis.text.x = element_text(angle = 40, hjust = 1))
    sg(p5, "pegu_components_top15.png", w = 12, h = 6)
  }
}

cat("[INFO] Generating plots...\n")
make_plots(df_out, df_f, output_dir)
cat("\n")


# ─────────────────────────────────────────────────────────────
# 7. CONSOLE SUMMARY
# ─────────────────────────────────────────────────────────────
cat("=============================================================\n")
cat("  PEGU GRADE DISTRIBUTION\n")
cat("=============================================================\n")
df_out %>% count(pegu_grade) %>% arrange(desc(n)) %>%
  as.data.frame() %>% print(row.names = FALSE)

cat("\n")
cat("=============================================================\n")
cat("  SARVAS SIGNAL DISTRIBUTION\n")
cat("=============================================================\n")
df_out %>% count(sarvas_signal) %>% arrange(desc(n)) %>%
  as.data.frame() %>% print(row.names = FALSE)

cat("\n")
cat("=============================================================\n")
cat(sprintf("  TOP 10 SARVAS PASS (Pegu >= 60, above both MAs, RSI neutral)\n"))
cat("=============================================================\n")
show_cols <- intersect(
  c("symbol", "exchange", "company_name", "sector",
    "last_price", "pe_ratio", "roe_pct",
    "pegu_score", "pegu_grade", "sarvas_score", "sarvas_signal"),
  names(df_f)
)
df_f %>%
  filter(sarvas_pass == TRUE) %>%
  arrange(desc(sarvas_score), desc(pegu_score)) %>%
  head(10) %>%
  select(all_of(show_cols)) %>%
  as.data.frame() %>%
  print(row.names = FALSE)

cat("\n")
cat("=============================================================\n")
cat(sprintf("  SECTOR LEADERS (avg Pegu score)\n"))
cat("=============================================================\n")
if (file.exists(file.path(output_dir, "sector_pegu_analysis.csv"))) {
  read_csv(file.path(output_dir, "sector_pegu_analysis.csv"),
           show_col_types = FALSE) %>%
    arrange(desc(avg_pegu)) %>%
    head(10) %>%
    select(sector, exchange, n_stocks, avg_pegu, n_buy, n_sarvas_pass) %>%
    as.data.frame() %>%
    print(row.names = FALSE)
}

cat(sprintf("\n[DONE] All outputs written to: %s/\n", output_dir))
