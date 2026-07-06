# Hybrid Approach - Complete Execution Guide

**Goal:** Create 100,000+ unified outlet database from PPAC + OpenStreetMap + Google Maps

**Total Time:** 1-2 hours (or 30 min with OSM only)

---

## 📋 Phase 1: Get PPAC Data (15 minutes)

### Step 1a: Visit PPAC Website
```
Website: https://ppac.gov.in/
```

### Step 1b: Navigate to Ready Reckoner
```
Home → Reports & Analysis → Ready Reckoner
```

### Step 1c: Download Retail Outlets CSV
```
Look for: "Retail Outlets" dataset
Format: Excel or CSV
File: Should contain columns like:
  - Outlet Name
  - Company (IOCL, BPCL, HPCL, Shell, Nayara)
  - State
  - City
  - Address
```

### Step 1d: Save to api-data-integration folder
```bash
# Move/save the file as:
/Users/umashankar/api-data-integration/ppac_retail_outlets.csv
```

**Verify:**
```bash
ls /Users/umashankar/api-data-integration/ppac_retail_outlets.csv
# Should show: ppac_retail_outlets.csv
```

---

## 📍 Phase 2: Run Hybrid Aggregation (30 minutes)

### Step 2a: Open Terminal
```bash
cd /Users/umashankar/api-data-integration
```

### Step 2b: Run Aggregation (PPAC + OSM - FREE)
```bash
python3 hybrid_aggregator.py --ppac-csv ./ppac_retail_outlets.csv
```

**What happens:**
1. Loads PPAC CSV (~95,000 outlets)
2. Fetches OpenStreetMap data (~80,000 outlets)
3. Combines both sources
4. Removes duplicates (within 0.5km)
5. Exports to multiple formats

**Expected output:**
```
🔄 HYBRID RETAIL OUTLET AGGREGATION
======================================================================

🏛️  Loading PPAC data...
  ✓ Loaded 95000 outlets

📍 Fetching OpenStreetMap data...
  ✓ Fetched 80000 OSM outlets

🔍 Deduplicating outlets...
  ✓ Removed 50000 duplicates
  ✓ Final unique outlets: 125000

💾 Exporting data...
  ✓ CSV: outlet_data_hybrid/hybrid_outlets_20260624.csv
  ✓ GeoJSON: outlet_data_hybrid/hybrid_outlets_20260624.geojson
  ✓ JavaScript: outlet_data_hybrid/hybrid_outlets_20260624.js
  ✓ Statistics: outlet_data_hybrid/hybrid_outlets_stats_20260624.json
```

**Time:** ~15-20 minutes (includes OSM API queries)

---

## 🌐 Phase 3 (Optional): Add Google Maps Data (60-90 minutes)

### If you want 100K+ outlets VERIFIED by Google:

```bash
python3 hybrid_aggregator.py \
    --ppac-csv ./ppac_retail_outlets.csv \
    --google-api-key YOUR_API_KEY
```

**Requirements:**
1. Google Cloud Console account (free)
2. Enable Google Places API
3. Create API Key
4. Budget: ~$15-50 for full India coverage

**Process:**
- 30 min: Setup Google API key
- 60 min: Run aggregation with Google (slower due to rate limits)
- Result: ~125,000 outlets with all 3 sources

---

## ✅ Phase 4: Verify Output (5 minutes)

### Step 4a: Check Output Folder
```bash
ls outlet_data_hybrid/
```

**Should show:**
```
hybrid_outlets_20260624_053600.csv
hybrid_outlets_20260624_053600.json
hybrid_outlets_20260624_053600.geojson
hybrid_outlets_20260624_053600.js
hybrid_outlets_stats_20260624_053600.json
```

### Step 4b: Check Statistics
```bash
cat outlet_data_hybrid/hybrid_outlets_stats_*.json
```

**Should show:**
```json
{
  "total_outlets": 125000,
  "with_coordinates": 125000,
  "states": 28,
  "cities": 500,
  "companies": 6,
  "sources": {
    "ppac": 95000,
    "osm": 80000,
    "google": 0
  },
  "duplicates_removed": 50000
}
```

### Step 4c: Check CSV (Optional)
```bash
head -5 outlet_data_hybrid/hybrid_outlets_*.csv
```

---

## 📍 Phase 5: Integrate with Maps (5 minutes)

### Step 5a: Copy JavaScript to Fuel Map
```bash
cp outlet_data_hybrid/hybrid_outlets_*.js \
   ../fuel-pump-locations-map/locations-data.js
```

### Step 5b: Verify Copy
```bash
ls -lah ../fuel-pump-locations-map/locations-data.js
# Should show file size ~15-20 MB
```

---

## 🧪 Phase 6: Test in Browser (5 minutes)

### Step 6a: Start Web Server
```bash
cd ../fuel-pump-locations-map/
python3 -m http.server 8000
```

**Output:**
```
Serving HTTP on 0.0.0.0 port 8000 (http://0.0.0.0:8000/) ...
```

### Step 6b: Open in Browser
```
Visit: http://localhost:8000
```

### Step 6c: Verify
- ✅ Map loads
- ✅ Outlets appear (may be clustered)
- ✅ Zoom in/out works
- ✅ Clustering shows counts
- ✅ Individual markers visible when zoomed
- ✅ No errors in console (F12)

---

## 💾 Phase 7: Commit to GitHub (10 minutes)

### Step 7a: Stage Changes
```bash
git add api-data-integration/outlet_data_hybrid/
git add fuel-pump-locations-map/locations-data.js
git status
```

**Should show:**
```
Changes to be committed:
  new file:   api-data-integration/outlet_data_hybrid/...
  modified:   fuel-pump-locations-map/locations-data.js
```

### Step 7b: Commit
```bash
git commit -m "Add hybrid aggregation: 100K+ outlets from PPAC+OSM"
```

### Step 7c: Push to GitHub
```bash
git push origin main
```

**Verify on GitHub:**
```
Visit: https://github.com/herrrickshaw/herrrickshaw
Check: outlet_data_hybrid/ folder exists with files
```

---

## 📊 Expected Results

### Data Statistics
```
Total Outlets: 100,000-130,000 (depending on sources)
├─ PPAC: 95,000-105,000 (official government)
├─ OpenStreetMap: 50,000-80,000 (crowdsourced)
├─ Google: 95,000 (if enabled)
└─ Duplicates Removed: 50,000-100,000
```

### Geographic Coverage
```
States: 28 (all major Indian states)
Union Territories: 8
Cities: 500+
Companies: 5 major (IOCL, BPCL, HPCL, Shell, Nayara) + Unknown (OSM)
```

### File Sizes
```
CSV: ~15 MB (spreadsheet compatible)
GeoJSON: ~20 MB (geographic format)
JavaScript: ~18 MB (web maps)
Total on Disk: ~50 MB
```

### Performance
```
Map Load Time: <3 seconds
Markers: 100,000+
Clustering: Automatic
Filter Response: <500ms
Browser Memory: 200-300 MB
```

---

## ⏱️ Timeline Breakdown

| Phase | Task | Duration |
|-------|------|----------|
| 1 | Download PPAC CSV | 15 min |
| 2 | Run hybrid aggregation | 20 min |
| 3 | (Optional) Google Maps setup | 30 min |
| 4 | Verify output files | 5 min |
| 5 | Integrate with maps | 5 min |
| 6 | Test in browser | 5 min |
| 7 | Commit to GitHub | 10 min |
| **TOTAL (OSM only)** | **60 min** | **1 hour** |
| **TOTAL (with Google)** | **2+ hours** | **2+ hours** |

---

## 🔧 Troubleshooting

### "File not found: ppac_retail_outlets.csv"
```bash
# Check if file exists
ls ppac_retail_outlets.csv

# If missing, download from ppac.gov.in and save to this directory
# Or use full path:
python3 hybrid_aggregator.py --ppac-csv /path/to/file.csv
```

### "OSM API rate limited (Status 406)"
```bash
# Wait 5-10 minutes and try again
# Or run with just PPAC data (skip OSM):
python3 hybrid_aggregator.py --ppac-csv ./ppac_retail_outlets.csv
# Will still work with PPAC alone
```

### "CSV file has wrong columns"
```bash
# Check column names:
head -1 ppac_retail_outlets.csv

# Script auto-handles common variations:
# - outlet_name, name, Outlet Name, Name
# - latitude, lat, Latitude
# - longitude, lng, Longitude
# - state, State, city, City
# - company, Company, operator
```

### "Map shows no outlets"
```bash
# 1. Check statistics file
cat outlet_data_hybrid/hybrid_outlets_stats_*.json

# 2. Verify total_outlets > 0
# 3. Check browser console (F12) for errors
# 4. Hard refresh browser: Ctrl+Shift+R
# 5. Clear cache and try again
```

### "Browser crashes with 100K+ markers"
```bash
# Leaflet handles this with clustering
# If still slow:
# 1. Close other browser tabs
# 2. Try on different browser
# 3. Try on more powerful machine
# 4. Or split data by region
```

---

## 🎯 Success Checklist

- [ ] Downloaded PPAC CSV from ppac.gov.in
- [ ] Saved to: api-data-integration/ppac_retail_outlets.csv
- [ ] Ran: python3 hybrid_aggregator.py --ppac-csv ./ppac_retail_outlets.csv
- [ ] Script completed without errors
- [ ] outlet_data_hybrid/ folder created with files
- [ ] Statistics show 100,000+ total outlets
- [ ] Copied JS file to fuel-pump-locations-map/
- [ ] Started test server: python3 -m http.server 8000
- [ ] Opened http://localhost:8000 in browser
- [ ] Outlets appear on map (clustered)
- [ ] Zoom/pan works
- [ ] No console errors (F12)
- [ ] Committed changes to git
- [ ] Pushed to GitHub (main branch)
- [ ] Verified on GitHub.com

---

## 🚀 Quick Commands Reference

```bash
# Phase 1: Navigate
cd /Users/umashankar/api-data-integration

# Phase 2: Run aggregation
python3 hybrid_aggregator.py --ppac-csv ./ppac_retail_outlets.csv

# Phase 4: Check results
cat outlet_data_hybrid/hybrid_outlets_stats_*.json

# Phase 5: Integrate
cp outlet_data_hybrid/hybrid_outlets_*.js \
   ../fuel-pump-locations-map/locations-data.js

# Phase 6: Test
cd ../fuel-pump-locations-map/
python3 -m http.server 8000
# Visit http://localhost:8000

# Phase 7: Commit
git add api-data-integration/outlet_data_hybrid/
git add fuel-pump-locations-map/locations-data.js
git commit -m "Add hybrid 100K+ outlet aggregation"
git push origin main
```

---

## 📞 Support

### For PPAC Download Issues:
- Website: https://ppac.gov.in/
- Email: ppac-mopng@nic.in
- Phone: +91-11-26740551

### For Script Issues:
- Check Python errors in console
- Verify PPAC CSV format
- Check internet connection for OSM fetch
- Review HYBRID_IMPLEMENTATION_GUIDE.md

---

## 🎯 Next Steps

**Ready? Let's execute:**

1. **Get PPAC CSV** from ppac.gov.in (15 min)
2. **Save to:** `api-data-integration/ppac_retail_outlets.csv`
3. **Run:** `python3 hybrid_aggregator.py --ppac-csv ./ppac_retail_outlets.csv`
4. **Follow prompts** (script does the rest)

---

**Estimated Total Time: 60 minutes for 100,000+ outlets**

Ready to start? Let's go! 🚀
