# Kaggle Dataset Quick Start

Using pre-compiled Indian Oil Retail Outlets dataset from Kaggle.

**Dataset:** https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025

## 🚀 3-Step Process (15 minutes)

### Step 1: Download Dataset (5 min)
1. Visit: https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025
2. Click **Download** button
3. Extract ZIP file to `api-data-integration/` directory
4. You should see a CSV file (usually named `indian_oil_outlets.csv`)

### Step 2: Load & Process (5 min)
```bash
cd api-data-integration/
python3 kaggle_loader.py indian_oil_outlets.csv
# Or with auto-detection:
python3 kaggle_loader.py
```

### Step 3: Integrate with Maps (5 min)
```bash
# Copy generated data to your map
cp outlet_data_kaggle/kaggle_outlets_LATEST.js \
   ../fuel-pump-locations-map/locations-data.js

# Or for gap analysis dashboard
cp outlet_data_kaggle/kaggle_outlets_LATEST.js \
   ../fuel-station-gap-analysis/data.js
```

## 📊 What You Get

- ✅ Pre-processed outlet locations
- ✅ Cleaned coordinates (latitude/longitude)
- ✅ State and city information
- ✅ Company identification
- ✅ Multiple export formats (CSV, GeoJSON, JavaScript)

## 📂 Output Files

```
outlet_data_kaggle/
├── kaggle_outlets_YYYYMMDD_HHMMSS.csv      # Standard CSV
├── kaggle_outlets_YYYYMMDD_HHMMSS.geojson  # GeoJSON for mapping
├── kaggle_outlets_YYYYMMDD_HHMMSS.json     # JSON format
├── kaggle_outlets_YYYYMMDD_HHMMSS.js       # JavaScript (for maps)
└── kaggle_outlets_stats_YYYYMMDD_HHMMSS.json # Statistics
```

## 🧪 Test After Loading

```bash
# Start test server
cd fuel-pump-locations-map/
python3 -m http.server 8000

# Open http://localhost:8000 and verify:
# ✓ Outlets appear on map
# ✓ Clustering works (zoom in/out)
# ✓ Filters work (state, company)
# ✓ Search works
# ✓ No console errors
```

## 💾 Commit to GitHub

```bash
git add outlet_data_kaggle/
git add fuel-pump-locations-map/locations-data.js
git commit -m "Add Kaggle Indian oil retail outlets dataset"
git push origin main
```

## Expected Results

- **Outlets:** 10,000-50,000+ (depending on Kaggle dataset)
- **States:** Multiple (likely all major states)
- **Quality:** Pre-verified and cleaned
- **Accuracy:** Depends on Kaggle source quality
- **Size:** ~5-15 MB JavaScript file

## Troubleshooting

### CSV File Not Found
```bash
# Check what files are in the directory
ls -la

# Run with full path
python3 kaggle_loader.py /path/to/file.csv
```

### Column Names Don't Match
The script automatically handles these variations:
- `outlet_name`, `name`, `Outlet Name`, `Name`
- `city`, `City`
- `state`, `State`
- `latitude`, `Latitude`, `lat`, `Lat`
- `longitude`, `Longitude`, `lng`, `Lng`
- `company`, `Company`, `operator`, `Operator`

If still having issues, check CSV columns:
```python
import pandas as pd
df = pd.read_csv('your_file.csv')
print(df.columns)
```

### Map Not Updating
Make sure to:
1. Copy the `.js` file to the correct directory
2. Clear browser cache (Ctrl+Shift+Delete)
3. Restart Python server
4. Hard refresh browser (Ctrl+Shift+R)

## Comparison: Kaggle vs Hybrid Approach

| Aspect | Kaggle | Hybrid |
|--------|--------|--------|
| **Time** | 15 min | 2+ hours |
| **Data Prep** | Pre-done ✅ | Manual (PPAC download) |
| **Deduplication** | Already done ✅ | Automatic via script |
| **Coverage** | 10K-50K+ | 100K+ (potential) |
| **Effort** | Minimal ⭐ | High |
| **Reliability** | High ✅ | High (3 sources) |

**Verdict:** Kaggle approach is faster and more practical for immediate results.

## Next Steps

1. ✅ Download Kaggle dataset
2. ✅ Run `python3 kaggle_loader.py`
3. ✅ Integrate with maps
4. ✅ Test in browser
5. ✅ Commit to GitHub
6. ⏭️ Deploy live maps

**Estimated Total Time: 15-30 minutes**

---

**Status:** Ready to execute
**Last Updated:** June 24, 2026
