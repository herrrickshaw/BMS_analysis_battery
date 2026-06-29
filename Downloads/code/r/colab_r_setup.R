# colab_r_setup.R
# ================
# Run this first in Google Colab (R kernel) to install all dependencies
# and verify the setup before running the three report scripts.
#
# In Colab: New notebook -> Runtime -> Change runtime type -> R

# ── Step 1: Install packages ──────────────────────────────────────────────────
pkgs_required <- c(
  "quantmod",    # Yahoo Finance OHLC + financial statements (replaces yfinance)
  "tidyquant",   # tq_get() wrapper (replaces yfinance + pandas)
  "dplyr",       # data manipulation (replaces pandas)
  "purrr",       # functional map (replaces Python list comprehensions)
  "readxl",      # Excel reading (replaces openpyxl)
  "openxlsx",    # Excel writing
  "lubridate",   # date arithmetic
  "jsonlite"     # JSON output
)

pkgs_parallel <- c(
  "furrr",       # parallel purrr — KEY for batch speedup
  "future"       # backend for furrr
)

install_if_missing <- function(pkgs) {
  missing <- pkgs[!sapply(pkgs, requireNamespace, quietly = TRUE)]
  if (length(missing) > 0) {
    cat(sprintf("Installing: %s\n", paste(missing, collapse = ", ")))
    install.packages(missing, repos = "https://cloud.r-project.org", quiet = TRUE)
  } else {
    cat("All packages already installed.\n")
  }
}

cat("=== Installing required packages ===\n")
install_if_missing(pkgs_required)

cat("\n=== Installing parallel packages (for batch speedup) ===\n")
install_if_missing(pkgs_parallel)

# ── Step 2: Load and verify ───────────────────────────────────────────────────
suppressPackageStartupMessages({
  library(quantmod); library(tidyquant); library(dplyr)
  library(purrr);    library(readxl);    library(jsonlite)
})
cat("\nCore packages loaded OK.\n")

parallel_ok <- all(sapply(pkgs_parallel, requireNamespace, quietly = TRUE))
cat(sprintf("Parallel processing: %s\n", if (parallel_ok) "AVAILABLE" else "NOT available (install furrr)"))

# ── Step 3: Quick connectivity test ──────────────────────────────────────────
cat("\n=== Testing Yahoo Finance connectivity ===\n")
test_sym <- "RELIANCE.NS"
tryCatch({
  df <- tq_get(test_sym, get = "stock.prices",
               from = Sys.Date() - 5, to = Sys.Date())
  if (!is.null(df) && nrow(df) > 0) {
    cat(sprintf("OK: %s — last close = %.2f\n", test_sym, tail(df$close, 1)))
  } else cat("WARNING: no data returned for", test_sym, "\n")
}, error = function(e) cat("ERROR:", conditionMessage(e), "\n"))

tryCatch({
  df2 <- tq_get("AAPL", get = "stock.prices",
                from = Sys.Date() - 5, to = Sys.Date())
  if (!is.null(df2) && nrow(df2) > 0)
    cat(sprintf("OK: AAPL — last close = %.2f\n", tail(df2$close, 1)))
}, error = function(e) cat("ERROR (AAPL):", conditionMessage(e), "\n"))

# ── Step 4: Usage guide ───────────────────────────────────────────────────────
cat("
=== USAGE GUIDE ===

--- Indian Stock Report ---
source('stock_daily_report.R')
run('RELIANCE')                        # text report
run('TCS', run_scans = TRUE)           # with Darvas + Piotroski + Coffee Can
run_nifty50_batch(run_scans = TRUE)    # all 50 Nifty stocks

--- US Stock Report ---
source('us_stock_daily_report.R')
run('AAPL')
run('NVDA', run_scans = TRUE)
run_batch(symbols = DOW_JONES_30)
run_batch(symbols = NASDAQ_50, run_scans = TRUE, n_workers = 4)

--- Batch Analysis (Indian, 305 stocks) ---
source('xlsx/batch_analysis.R')        # adjust path as needed
run_batch_excel()                      # sequential or parallel
run_batch_excel(n_workers = 4)         # ~4x faster with parallel
run_batch_excel(limit = 20)            # test with first 20 stocks
print_summary()                        # ranked summary from last CSV

=== PERFORMANCE vs PYTHON ===
Python (sequential, 1.5s sleep):  305 stocks ~ 45-60 min
R (furrr, 4 workers, no sleep):   305 stocks ~ 10-15 min
R (furrr, 8 workers, no sleep):   305 stocks ~  6-8  min
")
