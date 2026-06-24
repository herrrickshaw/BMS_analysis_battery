# Retail Outlet Data Integration

Multiple approaches to load comprehensive database of fuel retail outlets across India.

## 🚀 Quick Start - Kaggle Dataset (RECOMMENDED - 15 min)

**Dataset:** https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025

```bash
# 1. Download from Kaggle (click Download button)
# 2. Extract CSV to this directory
# 3. Load dataset
python3 kaggle_loader.py

# 4. Verify output
ls outlet_data_kaggle/

# 5. Integrate with maps
cp outlet_data_kaggle/kaggle_outlets_LATEST.js \
   ../fuel-pump-locations-map/locations-data.js

# 6. Test
cd ../fuel-pump-locations-map/
python3 -m http.server 8000
# Visit http://localhost:8000
```

**Full instructions:** See `KAGGLE_QUICK_START.md`

---

## Alternative Approaches

### Option A: Kaggle Dataset (FASTEST)
- ✅ **Time:** 15 minutes
- ✅ **Pre-processed:** Already cleaned
- ✅ **Coverage:** 10K-50K+ outlets
- ✅ **Effort:** Minimal
- ✅ **Cost:** Free
- 📄 **Guide:** `KAGGLE_QUICK_START.md`

### Option B: Hybrid Aggregation (MOST COMPREHENSIVE)
- 🔧 **Time:** 2+ hours
- 🔄 **Multi-source:** PPAC + OSM + Google
- 📊 **Coverage:** 100,000+ outlets (potential)
- 💪 **Effort:** Medium
- 💵 **Cost:** Free-$50
- 📄 **Guide:** `HYBRID_IMPLEMENTATION_GUIDE.md`

### Option C: Single Sources (FLEXIBLE)
- ⚡ **PPAC Official:** 95K outlets, free
- 🗺️ **OpenStreetMap:** 80K outlets, free
- 🌐 **Google Maps:** 95K outlets, $15-50
- 📄 **Guide:** `HYBRID_IMPLEMENTATION_GUIDE.md`

---

## Scripts Available

| Script | Purpose | Use When |
|--------|---------|----------|
| `kaggle_loader.py` | Load Kaggle CSV | You have Kaggle dataset (RECOMMENDED) |
| `hybrid_aggregator.py` | Combine multiple sources | You want 100K+ with deduplication |
| `integration.py` | Generic API framework | Adding custom data sources |
| `quick_start.sh` | Interactive wizard | Running hybrid approach |

---

## Data Formats Supported

### Input Formats
- CSV (Kaggle, PPAC, custom)
- JSON (APIs)
- GeoJSON (geographic data)
- XML (OpenStreetMap)

### Output Formats
- **CSV** - Standard tabular format
- **JSON** - Structured data format
- **GeoJSON** - Geographic features
- **JavaScript** - Web map integration
- **Statistics** - Coverage metadata

---

## Getting Data

### Kaggle Dataset
1. Visit: https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025
2. Click **Download**
3. Extract to this directory
4. Run: `python3 kaggle_loader.py`

### PPAC Data (Alternative)
1. Visit: https://ppac.gov.in/
2. Go to: Reports & Analysis → Ready Reckoner
3. Download: "Retail Outlets" CSV
4. Run: `python3 hybrid_aggregator.py --ppac-csv ./ppac_retail_outlets.csv`

### OpenStreetMap (Alternative)
1. Run: `python3 hybrid_aggregator.py`
2. Script auto-queries Overpass API

### Google Maps (Optional)
1. Get API key from: https://console.cloud.google.com/
2. Run: `python3 hybrid_aggregator.py --google-api-key YOUR_KEY`

---

## Expected Results

### Kaggle Approach
- Outlets: 10,000-50,000+ (depends on dataset)
- Time: 15 minutes
- Quality: Pre-verified
- Cost: Free

### Hybrid Approach (PPAC + OSM)
- Outlets: 100,000-110,000 (after dedup)
- Time: 1-2 hours
- Quality: 90-95% accuracy
- Cost: Free

### With Google Maps
- Outlets: 100,000-110,000 (verified)
- Time: 2-4 hours
- Quality: 95%+ accuracy
- Cost: $15-50

---

## Integration with Maps

### For Fuel Pump Locations Map
```bash
cp outlet_data_kaggle/kaggle_outlets_LATEST.js \
   ../fuel-pump-locations-map/locations-data.js
```

### For Fuel Gap Analysis Dashboard
```bash
cp outlet_data_kaggle/kaggle_outlets_LATEST.js \
   ../fuel-station-gap-analysis/data.js
```

### Manual Integration
```javascript
<script src="outlet_data_kaggle/kaggle_outlets_LATEST.js"></script>

// Use in your code
const outlets = FUEL_PUMP_LOCATIONS;  // Loaded from script
```

---

## Troubleshooting

### Kaggle CSV Not Found
```bash
# Check filenames
ls -la *.csv

# Run with explicit path
python3 kaggle_loader.py /path/to/file.csv
```

### Column Names Don't Match
Script handles:
- `outlet_name`, `name`, `Outlet Name`, etc.
- `latitude`, `lat`, `Latitude`, etc.
- `longitude`, `lng`, `Longitude`, etc.
- `state`, `State`, `city`, `City`
- `company`, `Company`, `operator`

### Map Not Loading
1. Clear browser cache
2. Hard refresh: Ctrl+Shift+R (or Cmd+Shift+R on Mac)
3. Restart Python server
4. Check browser console for errors

### Performance Issues (100K+ markers)
- Use Leaflet clustering (automatic)
- Test on more powerful machine
- Split data by regions if needed

---

## Technology Stack

- **Python 3.9+** - Data processing
- **Pandas** - DataFrames and CSV handling
- **Requests** - HTTP API queries
- **Leaflet.js** - Web maps
- **GeoJSON** - Geographic data standard

---

## Quick Comparison

| Feature | Kaggle | Hybrid | PPAC Only | OSM Only |
|---------|--------|--------|-----------|----------|
| **Time** | 15 min | 2 hrs | 1 hr | 30 min |
| **Coverage** | 10-50K | 100K+ | 95K | 80K |
| **Accuracy** | Pre-verified | 90-95% | 95% | 85% |
| **Cost** | Free | Free-$50 | Free | Free |
| **Effort** | Minimal ⭐ | Medium | Low | Low |
| **Setup** | Easiest ⭐ | Complex | Medium | Easy |

---

## Related Documentation

- 📍 **Fuel maps:** `../fuel-pump-locations-map/`
- 📊 **Gap analysis:** `../fuel-station-gap-analysis/`
- 📋 **Data sources:** `../data-sources/`
- 🚗 **Toll plazas:** `../toll-plaza-visualization/`
- 📖 **Main README:** `../README.md`

---

## Next Steps

1. **Choose approach:** Kaggle (fastest) or Hybrid (most comprehensive)
2. **Get data:** Download from source
3. **Process:** Run appropriate script
4. **Verify:** Check output statistics
5. **Integrate:** Copy to map directory
6. **Test:** Start server and verify in browser
7. **Commit:** Push to GitHub

---

**Status:** Ready for Implementation
**Last Updated:** June 24, 2026
**Recommendation:** Start with Kaggle (15 min), then consider Hybrid (2+ hours) if you need 100K+ outlets

🚀 **Ready to load outlet data?** Pick your approach above and start!
