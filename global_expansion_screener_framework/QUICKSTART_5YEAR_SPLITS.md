# Quick Start: 5-Year Batch Splits
## Store 15-Year Data as 3 Separate Files

---

## 🎯 WHAT'S DIFFERENT

### Traditional Approach (1 File)
```
india_stocks_15y_full.db.gz
  └─ 831 MB (all 15 years: 2011-2026)
  └─ Single download
  └─ Monolithic storage
```

### 5-Year Split Approach (3 Files) ✅
```
india_stocks_2011_2015.db.gz
  └─ ~277 MB (Period 1: 2011-2015)
  
india_stocks_2016_2020.db.gz
  └─ ~277 MB (Period 2: 2016-2020)
  
india_stocks_2021_2026.db.gz
  └─ ~277 MB (Period 3: 2021-2026)
  
TOTAL: ~831 MB (same total, split across 3 files)
```

---

## 📋 BENEFITS

### Modularity
- ✅ **Independent periods** - use only what you need
- ✅ **Selective analysis** - analyze specific time windows
- ✅ **Easier management** - smaller individual files
- ✅ **Faster downloads** - can get one period quickly

### Recovery & Resilience
- ✅ **Parallel execution** - run period batches separately
- ✅ **Individual checkpoints** - per-period recovery points
- ✅ **Partial updates** - refresh one period without re-running all
- ✅ **Storage flexibility** - pick which periods to store locally

### Use Cases
- ✅ **Phase 2 Analysis** - calibrate on 2011-2015, validate on 2016-2026
- ✅ **Factor analysis** - analyze trends within each 5-year window
- ✅ **Performance tracking** - separate recent vs historical performance
- ✅ **Development** - work with smaller datasets during dev

---

## 🚀 EXECUTION: 3 Simple Commands

### Step 1: Run 5-Year Batch Split
```bash
python3 run_batch_5year_splits.py

# Produces 3 files:
# ✅ india_stocks_2011_2015.db (~420 MB)
# ✅ india_stocks_2016_2020.db (~420 MB)
# ✅ india_stocks_2021_2026.db (~420 MB)
```

**Timeline:**
- Per period: ~2.8-3.5 hours
- All 3 periods sequential: ~8-10 hours
- Or run periods in parallel (separate machines): ~2.8-3.5 hours

### Step 2: Compress Each File
```bash
# Compress all 3 files
gzip -9 india_stocks_2011_2015.db
gzip -9 india_stocks_2016_2020.db
gzip -9 india_stocks_2021_2026.db

# Results:
# india_stocks_2011_2015.db.gz (~277 MB)
# india_stocks_2016_2020.db.gz (~277 MB)
# india_stocks_2021_2026.db.gz (~277 MB)
# TOTAL: ~831 MB
```

### Step 3: Push to GitHub LFS
```bash
# Add to Git
git add india_stocks_*.db.gz

# Commit
git commit -m "feat: 15-year data in 3 separate 5-year files (831MB total)

- Period 1 (2011-2015): 277 MB
- Period 2 (2016-2020): 277 MB  
- Period 3 (2021-2026): 277 MB

Stored in Git LFS for efficient distribution"

# Push to GitHub
git push origin global-expansion-screener-v3.1
```

---

## 📊 3 FILES BREAKDOWN

### File 1: india_stocks_2011_2015.db.gz
```
Time Period:   2011-01-01 to 2015-12-31 (5 years)
Trading Days:  ~1,260 per stock
Records:       ~3.36 million (2,681 stocks × 1,260 days)
Uncompressed:  ~420 MB
Compressed:    ~267 MB (63.3% ratio)
Use Case:      Factor calibration period
```

### File 2: india_stocks_2016_2020.db.gz
```
Time Period:   2016-01-01 to 2020-12-31 (5 years)
Trading Days:  ~1,260 per stock
Records:       ~3.36 million (2,681 stocks × 1,260 days)
Uncompressed:  ~420 MB
Compressed:    ~267 MB (63.3% ratio)
Use Case:      Validation period 1
```

### File 3: india_stocks_2021_2026.db.gz
```
Time Period:   2021-01-01 to 2026-06-30 (5.5 years)
Trading Days:  ~1,320 per stock
Records:       ~3.54 million (2,681 stocks × 1,320 days)
Uncompressed:  ~445 MB
Compressed:    ~281 MB (63.3% ratio)
Use Case:      Validation period 2 + recent data
```

---

## 💡 USAGE SCENARIOS

### Scenario 1: Full 15-Year Analysis
```python
import sqlite3
import pandas as pd

# Load all 3 periods
dfs = []
for period in ['2011_2015', '2016_2020', '2021_2026']:
    db = f'india_stocks_{period}.db'
    conn = sqlite3.connect(db)
    df = pd.read_sql_query("SELECT * FROM prices", conn)
    dfs.append(df)
    conn.close()

# Combine
full_data = pd.concat(dfs)
# Now have 15-year data from 3 files
```

### Scenario 2: Phase 2 Calibration (2011-2015 only)
```python
import sqlite3

conn = sqlite3.connect('india_stocks_2011_2015.db')
cursor = conn.cursor()

# Calibrate factors using 2011-2015
cursor.execute("""
    SELECT symbol, date, close FROM prices 
    WHERE date >= '2011-01-01' AND date <= '2015-12-31'
    ORDER BY symbol, date
""")
calibration_data = cursor.fetchall()

# Use for factor weight regression
# coefficients = fit_factors(calibration_data)

conn.close()
```

### Scenario 3: Incremental Updates
```bash
# Update only 2021-2026 with latest data
# Re-run just Period 3:
python3 run_batch_5year_splits.py --period 3

# Only processes Period 3, saves time & bandwidth
# Keep Periods 1-2 unchanged
```

### Scenario 4: Development with Reduced Data
```bash
# For testing, only download Period 3 (recent data)
# Faster: 2.8-3.5 hours vs 8-10 hours
# Storage: 281 MB vs 831 MB

gunzip india_stocks_2021_2026.db.gz
python3 -c "
import sqlite3
conn = sqlite3.connect('india_stocks_2021_2026.db')
print(pd.read_sql_query(
    'SELECT COUNT(*) FROM prices',
    conn
))
"
```

---

## 📈 FILE DOWNLOAD & MANAGEMENT

### GitHub LFS Storage
```
Total Storage:      ~831 MB (3 files combined)
GitHub LFS Quota:   1 GB/month (FREE) ✅
Download Time:      
  Single file:      ~3 minutes (100 Mbps)
  All 3 files:      ~9 minutes (sequential)
  Parallel:         ~3 minutes (if downloading from 3 sources)
```

### Selective Download
```bash
# Download only what you need
git lfs pull --include="india_stocks_2011_2015.db.gz"  # 267 MB

# Or all
git lfs pull  # 831 MB
```

### Storage Strategy
```
Local Development:
  Development:     Use Period 3 only (recent data, smallest)
  Testing:         Use Period 1 only (historical data)
  Production:      Use all 3 periods (full 15 years)

Cloud/CI:
  Store:           All 3 files in GitHub LFS
  Fetch as needed: Only required periods
  Cache:           Period 3 (most frequently used)
```

---

## ✅ EXECUTION CHECKLIST

### Pre-Execution
- [ ] Git LFS installed and configured
- [ ] `.gitattributes` includes `*.db.gz` tracking
- [ ] 1.5 GB free disk space (per period)
- [ ] Network connection stable

### Execution
- [ ] Run: `python3 run_batch_5year_splits.py`
- [ ] Monitor 3 periods completing sequentially
- [ ] Each period creates checkpoint directory
- [ ] No errors in output

### Post-Execution
- [ ] 3 uncompressed `.db` files created
- [ ] Record counts match expectations (~3.36M each)
- [ ] Compress all 3: `gzip -9 india_stocks_*.db`
- [ ] Verify compressed files (~267-281 MB each)
- [ ] Push to GitHub LFS: `git push origin`

### Verification
- [ ] `git lfs ls-files` shows 3 files
- [ ] Each file ~267-281 MB
- [ ] Total ~831 MB
- [ ] Files available for download

---

## 📊 ADVANTAGES vs DISADVANTAGES

### 5-Year Splits (3 Files) ✅
**Advantages:**
- ✅ Modular & flexible
- ✅ Smaller individual files
- ✅ Selective downloads
- ✅ Easier to manage
- ✅ Can parallelize execution
- ✅ Incremental updates

**Trade-offs:**
- ❌ More files to manage
- ❌ Need to combine for full analysis
- ❌ Longer initial execution (sequential)

### Single File (1 File)
**Advantages:**
- ✅ Single download
- ✅ Simpler management
- ✅ No merging needed

**Trade-offs:**
- ❌ Less flexible
- ❌ Larger file (831 MB)
- ❌ Can't selectively update
- ❌ All-or-nothing approach

---

## 🎯 RECOMMENDATION

**For this project, use 5-Year Splits because:**

1. **Phase 2 Analysis** needs to:
   - Calibrate on 2011-2015
   - Validate on 2016-2026
   - Having separate files makes this explicit

2. **Factor Regression** benefits from:
   - Clear separation of time windows
   - Ability to analyze each 5-year period independently
   - Easy to run separate analyses per period

3. **Development Efficiency**:
   - Can work with Period 3 (recent) while waiting for full load
   - Faster iteration cycles
   - Smaller test datasets

4. **Storage & Distribution**:
   - 3 × 267 MB files = flexible distribution
   - Users can download only needed periods
   - Easier incremental updates

---

## 🚀 COMMANDS REFERENCE

```bash
# Test mode (100 stocks, quick validation)
python3 run_batch_5year_splits.py --test

# Full production (2,681 stocks, ~8-10 hours)
python3 run_batch_5year_splits.py

# Compress all 3 files
gzip -9 india_stocks_*.db

# Push to GitHub LFS
git add india_stocks_*.db.gz
git commit -m "feat: 15-year data in 3 separate 5-year files"
git push origin global-expansion-screener-v3.1

# Verify LFS
git lfs ls-files

# Download only Period 1 (during development)
git lfs pull --include="india_stocks_2011_2015.db.gz"

# Download all periods (for production)
git lfs pull
```

---

## ⏱️ TIMELINE

### Full Execution (Sequential)
```
Period 1 (2011-2015):    2.8-3.5 hours + compression + push
Period 2 (2016-2020):    2.8-3.5 hours + compression + push
Period 3 (2021-2026):    2.8-3.5 hours + compression + push
────────────────────────────────────────────────────────────
TOTAL:                   8.5-10.5 hours (can overlap with monitoring)
```

### Parallel Execution (3 Machines)
```
All periods:             2.8-3.5 hours + compression + push
(If using 3 separate machines or cloud instances)
```

---

## 📞 NEXT STEPS

1. **Execute:** `python3 run_batch_5year_splits.py`
2. **Monitor:** Database growth in each period
3. **Compress:** All 3 files with `gzip -9`
4. **Store:** Push all 3 to GitHub LFS
5. **Analyze:** Begin Phase 2 with organized, modular data

---

**Status: ✅ Ready for 5-Year Split Execution**  
**Timeline:** 8.5-10.5 hours (sequential) or 2.8-3.5 hours (parallel)  
**Output:** 3 files × 267-281 MB = 831 MB total  
**Benefit:** Modular, flexible, easy to manage!
