# Archived & Legacy Projects

> Historical projects and inactive branches. These are preserved for reference but no longer actively maintained.

---

## 🗂️ Archived Branches

These branches contain older feature work and can be reviewed for reference:

### UI/Infrastructure Branches
- `circleci-project-setup` — Old CI/CD pipeline configuration
- `feature/geography-status` — Geographic data status tracking
- `feature/hong-kong-canada` — Regional expansion exploration

### Feature Explorations
- `claude/bms-battery-management-y26x71` — Battery management research
- `claude/code-style-kubernetes-era-md2q57` — K8s deployment patterns
- `claude/event-driven-stock-news-msv0cq` — Event-driven architecture
- `claude/nse-bse-pegu-scoring-k7vu9` — NSE/BSE scoring model
- `claude/portfolio-beta-efficient-frontier-xJltY` — Beta-efficient frontier
- `claude/put-call-parity-trading-QMSlQ` — Options trading
- `claude/stock-metrics-nse-extraction-di4v0` — Metrics extraction
- `claude/surge-pricing-transport-mrwpsl` — Dynamic pricing model

### Experimental Features
- `feature/darvas-interpreter` — Darvas box chart interpretation
- `feature/multi-source-data` — Multi-source data aggregation
- `feature/scanner-optimise` — Screener performance optimization

**Note:** To restore work from these branches:
```bash
git checkout <branch-name>
git checkout -b new-feature-name  # Create new branch from it
```

---

## 🏭 Legacy Projects (Archived Locally)

The following projects are preserved in local storage but not tracked in this repo:

### 1. Fuel Infrastructure Suite
📁 `/Users/umashankar/toll_*` and `/Users/umashankar/fuel_*` (local only)

**Projects:**
- Toll plaza traffic & collection visualization (1,402 plazas)
- Fuel station gap analysis dashboard
- Fuel pump locations interactive map
- EV charging network mapping

**Status:** Local reference only (not in git)  
**Reason:** Infrastructure data project separate from stock analysis focus  

**Quick Links (Local):**
```bash
# Toll plaza analysis
cd ~/toll_plaza_visualization/
python3 toll_plaza_visualization.py
python3 toll_plaza_dashboard.py

# Fuel stations
cd ~/fuel-station-gap-analysis/
python3 -m http.server 8000  # http://localhost:8000
```

---

## 📊 Data Archives

### SSRI Retail Outlet Data
- **107,000 SSRI fuel pump retail outlets**
- **Status:** Local archive (`~/outlet_data_ssri_107k/`)
- **Extraction Guides:**
  - `SSRI_API_DATA_EXTRACTION.md` — API setup
  - `SSRI_100K_INTEGRATION_GUIDE.md` — Full workflow
  - `SSRI_COMPLETE_EXTRACTION_REPORT.md` — Results

### BPCL Regional Data
- **Status:** Local archive (`~/outlet_data_bpcl/`)
- **Guide:** `extract_bpcl_regional_dealerships.py`

### Toll Plaza Data
- **1,402 toll plazas** across 28 states
- **Status:** Local visualization assets
- **Dashboard:** HTML maps (2024-01 through 2024-11)

---

## 📚 Documentation Archive

These documents supported the archived projects:

| Document | Project | Status |
|----------|---------|--------|
| `FUEL_PUMP_LOCATIONS_MAP_SUMMARY.md` | Fuel mapping | Reference |
| `FUEL_STATION_DASHBOARD_SUMMARY.md` | Gap analysis | Reference |
| `TOLL_PLAZA_VISUALIZATION_GUIDE.md` | Toll analysis | Reference |
| `TOLL_RETAIL_INTEGRATION_SUMMARY.md` | Multi-modal | Reference |
| `RETAIL_OUTLETS_DATA_SOURCES.md` | Outlet sourcing | Reference |
| `SEASONAL_ANALYSIS_GUIDE.md` | Traffic patterns | Reference |
| `KAGGLE_IMPLEMENTATION_SUMMARY.md` | Kaggle sourcing | Reference |
| `DATA_INTEGRATION_OPTIONS.md` | Multi-source merge | Reference |
| `COMPLETE_SYSTEM_SUMMARY.md` | Full system | Reference |

---

## 🔄 Why These Are Archived

1. **Focus Shift:** Project pivoted to quantitative stock analysis (global markets, fundamental screening)
2. **Separate Goals:** Infrastructure/fuel projects are geospatial; stock analysis is financial
3. **Data Independence:** Retail outlet data is massive (~100K+ rows) and better managed separately
4. **Maintenance:** Single-focus repo reduces complexity and improves security

---

## ♻️ How to Revive

If you want to reactivate any archived project:

### From a branch:
```bash
git checkout -b revival/<project-name> <branch-name>
# Make changes
git push origin revival/<project-name>
```

### From local archives:
```bash
# Copy back to repo
cp -r ~/outlet_data_ssri_107k/ ./data/archived/retail_outlets/

# Create branch
git checkout -b feature/restore-<project>
git add data/archived/
git commit -m "restore: <project-name>"
git push origin feature/restore-<project>
```

---

## 📋 Summary

**Active:** Stock analysis system (NSE/BSE/NASDAQ/NYSE/Global)  
**Inactive Branches:** 15+ feature/claude explorations  
**Archived Data:** Toll, fuel, retail outlets (local)  
**Preserved Docs:** Infrastructure guides (reference)

For current work, see [README.md](./README.md).
