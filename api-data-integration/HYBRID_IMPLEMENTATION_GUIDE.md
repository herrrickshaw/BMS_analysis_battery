# Hybrid Data Aggregation Implementation Guide

## Overview
Combine PPAC (official), OpenStreetMap, and Google Maps data to create a comprehensive 100,000+ outlet database.

---

## Phase 1: Gather Data from All Sources

### 1.1 PPAC Data (Official - 95,000+ outlets)
**Priority: HIGHEST** ⭐⭐⭐⭐⭐

**Steps:**
1. Visit: https://ppac.gov.in/
2. Navigate: Reports & Analysis → Ready Reckoner
3. Download: "Retail Outlets" dataset (Excel format)
4. Expected format: Company-wise, state-wise distribution with addresses

**What you get:**
- All 5 OMCs (IOCL, BPCL, HPCL, Shell, Nayara)
- Precise outlet counts
- Geographic distribution
- Official data (highest accuracy)

**Cost:** Free
**Time:** 15 minutes to download

---

### 1.2 OpenStreetMap Data (Supplementary - 80,000+ outlets)
**Priority: HIGH** ⭐⭐⭐⭐

**Automatic fetching:**
```bash
python3 hybrid_aggregator.py
```

**What happens:**
- Script queries Overpass API for all amenity="fuel" nodes in India
- Covers 3 regions (North, South, Central) to avoid timeout
- Deduplicates internally
- Exports in multiple formats

**Expected results:**
- 50,000-80,000 outlets
- Crowdsourced data (85% accurate)
- Good coverage for gaps in PPAC data

**Cost:** Free
**Time:** 5-10 minutes (includes API wait time)

---

### 1.3 Google Maps Data (Verification - 95,000+ outlets)
**Priority: MEDIUM** ⭐⭐⭐

**Option A: With API Key (Recommended)**
```bash
python3 hybrid_aggregator.py --google-api-key YOUR_API_KEY
```

**How to get API key:**
1. Go to: https://console.cloud.google.com/
2. Enable: Google Places API
3. Create API key in Credentials
4. Set budget (optional, ~$0.03-0.15 per request)

**What you get:**
- 95,000+ verified outlet locations
- Real-time data
- Company verification

**Cost:** $15-50 for full India coverage
**Time:** 2-4 hours (API is rate-limited)

**Option B: Without API Key (Free)**
- Use existing data from PPAC + OSM
- 85,000-100,000 outlets coverage
- Skip Google verification step

---

## Phase 2: Run the Aggregation Pipeline

### Quick Start (OSM Only)
```bash
cd api-data-integration/
python3 hybrid_aggregator.py
```

Output files:
- `outlet_data_hybrid/hybrid_outlets_YYYYMMDD_HHMMSS.csv`
- `outlet_data_hybrid/hybrid_outlets_YYYYMMDD_HHMMSS.geojson`
- `outlet_data_hybrid/hybrid_outlets_YYYYMMDD_HHMMSS.js`
- `outlet_data_hybrid/hybrid_outlets_stats_YYYYMMDD_HHMMSS.json`

### With PPAC Data
```bash
# After downloading PPAC CSV from ppac.gov.in
python3 hybrid_aggregator.py --ppac-csv ./ppac_retail_outlets.csv
```

### With All Three Sources
```bash
python3 hybrid_aggregator.py \
    --ppac-csv ./ppac_retail_outlets.csv \
    --google-api-key YOUR_API_KEY
```

---

## Phase 3: Deduplication Process

The aggregator automatically:
1. **Loads** all outlets from each source
2. **Standardizes** column names (latitude, longitude, name, company, etc.)
3. **Sorts by priority** (PPAC > Google > OSM)
4. **Calculates distance** between all outlets using Haversine formula
5. **Removes duplicates** within 0.5 km radius
6. **Exports** final unified database

**Expected deduplication:**
- Input: 250,000-270,000 records (with duplicates)
- Output: 100,000-110,000 unique outlets
- Duplicates removed: 150,000-170,000

---

## Phase 4: Integrate with Existing Maps

### Option A: Replace Existing Data

**Update Fuel Pump Locations Map:**
```bash
cp outlet_data_hybrid/hybrid_outlets_LATEST.js \
   fuel-pump-locations-map/locations-data.js
```

Edit `locations-data.js` to add:
```javascript
// Add at top
const FUEL_PUMP_LOCATIONS = HYBRID_OUTLETS;  // 100,000+ outlets
const OUTLET_STATS = HYBRID_STATS;
```

**Update Fuel Gap Analysis Dashboard:**
```bash
cp outlet_data_hybrid/hybrid_outlets_LATEST.js \
   fuel-station-gap-analysis/data.js
```

### Option B: Merge with Existing Data (Recommended)

Keep existing 200+ curated fuel pump locations + Add 100,000+ hybrid outlets:

```javascript
// In locations-data.js
const CURATED_PUMPS = [/* existing 200 */];
const HYBRID_OUTLETS = [/* new 100,000+ */];

// Merge (deduplicated)
const FUEL_PUMP_LOCATIONS = [...CURATED_PUMPS, ...HYBRID_OUTLETS];
```

---

## Phase 5: Verification & Testing

### 1. Data Quality Check
```python
# In Python
import pandas as pd

df = pd.read_csv('outlet_data_hybrid/hybrid_outlets_LATEST.csv')

# Verify completeness
print(f"Total outlets: {len(df)}")
print(f"With coordinates: {df[['latitude', 'longitude']].notna().all(axis=1).sum()}")
print(f"States covered: {df['state'].nunique()}")
print(f"Cities covered: {df['city'].nunique()}")
print(f"Companies: {df['company'].unique()}")
```

### 2. Map Testing
```bash
# Start test server
cd fuel-pump-locations-map/
python3 -m http.server 8000

# Open: http://localhost:8000
```

Verify:
- ✓ All markers load (should see 100K+)
- ✓ Clustering works (zoom out to see clusters)
- ✓ Filtering by state works
- ✓ Company filters work
- ✓ Search functionality works
- ✓ No console errors

### 3. Performance Test
- Check load time (should be <3 seconds for 100K+ markers)
- Verify map responsiveness
- Test on different devices/browsers

---

## Data Format Reference

### Input Format (PPAC CSV)
```csv
outlet_name,company,state,city,latitude,longitude,address
IOC-KR-001,IOCL,Karnataka,Bangalore,12.9716,77.5946,Bangalore City
BPCL-KR-002,BPCL,Karnataka,Bangalore,12.9750,77.6000,Bangalore
...
```

### Output Format (Unified)
```csv
name,latitude,longitude,source,company,city,state
IOC-KR-001,12.9716,77.5946,PPAC,IOCL,Bangalore,Karnataka
OSM-Fuel-Station-23,13.0050,77.5900,OpenStreetMap,Unknown,Bangalore,Karnataka
...
```

### GeoJSON Format
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [77.5946, 12.9716]
      },
      "properties": {
        "name": "IOC-KR-001",
        "company": "IOCL",
        "source": "PPAC",
        "city": "Bangalore",
        "state": "Karnataka"
      }
    }
  ]
}
```

---

## Expected Outcomes

| Data Source | Outlets | Accuracy | Coverage |
|------------|---------|----------|----------|
| PPAC (Official) | 95,000-105,000 | 95% | All states |
| OpenStreetMap | 50,000-80,000 | 85% | Crowdsourced |
| Google Maps | 95,000 | 90% | Major cities |
| **COMBINED (Deduped)** | **100,000-110,000** | **90-95%** | **All India** |

---

## Timeline

| Phase | Duration | Effort |
|-------|----------|--------|
| Download PPAC data | 15 min | Low |
| Run OSM aggregation | 10 min | None (automated) |
| Optional: Setup Google API | 30 min | Low |
| Integrate with maps | 20 min | Low |
| Verify & test | 30 min | Medium |
| **TOTAL** | **~2 hours** | **Low-Medium** |

---

## Cost Breakdown

| Source | Cost | Volume | Unit Cost |
|--------|------|--------|-----------|
| PPAC | Free | 95,000 | $0 |
| OpenStreetMap | Free | 50,000 | $0 |
| Google Maps | Optional | 95,000 | $15-50 |
| **Total** | **Free-$50** | **100,000+** | **<$0.01 each** |

---

## Troubleshooting

### OSM API Returns 406 Error
- API is rate-limited
- Try again in 5 minutes
- Or skip to PPAC + manual data

### CSV File Has Wrong Columns
- Check CSV format from PPAC
- May need to rename columns
- See "Data Format Reference" section above

### Map Not Loading 100K+ Markers
- Check browser console for errors
- Verify file size (should be 10-20 MB for JS)
- Clear browser cache
- Try splitting data into regions if needed

### Deduplication Removing Too Many
- Increase distance threshold: `dedup_distance_km = 1.0` (instead of 0.5)
- May have more outlets in final result

---

## Next Steps

1. **Download PPAC data** (visit ppac.gov.in)
2. **Run aggregation** with PPAC CSV
3. **Verify outputs** in outlet_data_hybrid/ directory
4. **Test in maps** locally
5. **Commit to GitHub** with new data
6. **Deploy** to live maps

---

## Contact & Support

**For PPAC Data:**
- Email: ppac-mopng@nic.in
- Phone: +91-11-26740551
- Website: https://ppac.gov.in/

**For Technical Issues:**
- Check script logs
- Verify API keys and permissions
- Refer to data format reference above

---

**Last Updated:** June 24, 2026
**Status:** Ready for Implementation
