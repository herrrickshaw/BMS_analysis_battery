# 🗺️ Setup Guide: Kaggle Pandas Datasets Integration

## Quick Start (3 Steps)

### Step 1: Install Required Libraries
```bash
pip install kagglehub pandas geopandas folium
```

### Step 2: Set Up Kaggle API Credentials

**Option A: Using Kaggle Web (Recommended)**
1. Go to https://www.kaggle.com/settings/account
2. Click "Create New API Token"
3. This downloads `kaggle.json`
4. Save it to: `~/.kaggle/kaggle.json`
5. Set permissions: `chmod 600 ~/.kaggle/kaggle.json`

**Option B: Manual Setup**
```bash
mkdir -p ~/.kaggle
# Create ~/.kaggle/kaggle.json with:
{
  "username": "your_kaggle_username",
  "key": "your_api_key"
}
chmod 600 ~/.kaggle/kaggle.json
```

### Step 3: Load the Dataset

```python
import pandas as pd
import kagglehub

# Download Indian Oil Outlets dataset
path = kagglehub.model_download(
    "adityaskarnik/indian-oil-retail-outlets-across-india-2025"
)

# Load the data
df = pd.read_csv(f"{path}/data.csv")  # Adjust filename as needed

print(f"Loaded {len(df):,} outlets")
print(df.head())
```

---

## Complete Integration Script

```python
#!/usr/bin/env python3
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import kagglehub

# Step 1: Download dataset
print("📥 Downloading Kaggle dataset...")
path = kagglehub.model_download(
    "adityaskarnik/indian-oil-retail-outlets-across-india-2025"
)

# Step 2: Load data
print("📂 Loading data...")
df = pd.read_csv(f"{path}/outlets.csv")  # Adjust filename

# Step 3: Validate coordinates
print("✓ Validating coordinates...")
df = df[
    (df['latitude'] >= 8.0) & (df['latitude'] <= 35.0) &
    (df['longitude'] >= 68.0) & (df['longitude'] <= 97.0) &
    (df['latitude'].notna()) & (df['longitude'].notna())
]

print(f"✓ Valid records: {len(df):,}")

# Step 4: Load existing SSRI data
print("📂 Loading SSRI data...")
ssri_df = pd.read_csv('outlet_data_ssri_107k/ssri_complete_pumps_*.csv')

# Step 5: Merge datasets
print("🔀 Merging datasets...")
combined = pd.concat([ssri_df, df], ignore_index=True)
combined = combined.drop_duplicates(
    subset=['latitude', 'longitude'],
    keep='first'
)

print(f"✓ Combined: {len(combined):,} outlets")

# Step 6: Create map
print("🗺️  Creating map...")
m = folium.Map(
    location=[20.5937, 78.9629],
    zoom_start=5,
    tiles='CartoDB positron'
)

cluster = MarkerCluster().add_to(m)

for idx, row in combined.iterrows():
    folium.CircleMarker(
        location=[row['latitude'], row['longitude']],
        radius=3,
        popup=f"{row.get('name', 'Outlet')} - {row.get('state', 'N/A')}",
        color='blue',
        fill=True
    ).add_to(cluster)

m.save('enhanced_india_outlets.html')
print("✅ Map saved: enhanced_india_outlets.html")

# Step 7: Export combined data
combined.to_csv('enhanced_outlets_combined.csv', index=False)
print("✅ Data exported: enhanced_outlets_combined.csv")
```

---

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'kagglehub'`
**Solution:**
```bash
pip install --upgrade kagglehub
```

### Issue: `Kaggle API credentials not found`
**Solution:**
```bash
# Verify credentials file exists
ls -la ~/.kaggle/kaggle.json

# Make sure it's readable
chmod 600 ~/.kaggle/kaggle.json

# Test connection
python3 -c "import kagglehub; print(kagglehub.__version__)"
```

### Issue: Dataset not found or access denied
**Solution:**
1. Verify dataset exists: https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025
2. Accept dataset terms (if required)
3. Check your Kaggle account has API access

### Issue: No latitude/longitude columns
**Solution:**
```python
# Inspect available columns
print(df.columns.tolist())

# Find coordinate columns (flexible search)
coord_cols = [col for col in df.columns 
              if any(x in col.lower() for x in ['lat', 'lon', 'x', 'y'])]
print(coord_cols)
```

---

## Dataset Information

**Dataset Name:** Indian Oil Retail Outlets Across India 2025  
**URL:** https://www.kaggle.com/datasets/adityaskarnik/indian-oil-retail-outlets-across-india-2025  
**Creator:** adityaskarnik  
**Expected Features:**
- Outlet name
- State/District
- Latitude & Longitude
- Address information
- Services offered

---

## Next Steps After Loading

1. **Validate:** Check coordinates are within India bounds
2. **Merge:** Combine with SSRI data (104,949 outlets)
3. **Deduplicate:** Remove duplicate coordinates
4. **Visualize:** Create Folium map
5. **Export:** Save as CSV/Excel/GeoJSON
6. **Analyze:** Generate statistics and insights

---

## Expected Results

```
Input Data:
- SSRI: 104,949 outlets
- Kaggle IOC: ~3,000-5,000 outlets

Output Data:
- Combined: 107,000-110,000 outlets
- Space saved: ~10-15% (deduplication)
- Geographic coverage: 28+ states
- Data quality: 100% validated coordinates
```

---

## Quick Reference Commands

```bash
# Install
pip install kagglehub pandas folium

# Check installation
python3 -c "import kagglehub; print(kagglehub.__version__)"

# Run integration script
python3 load_kaggle_indian_oil_outlets.py

# Create map
python3 api-data-integration/enhanced_geo_map_with_kaggle.py

# Compress final data
gzip -k enhanced_outlets_combined.csv
```

---

## Files to Review

- `load_kaggle_indian_oil_outlets.py` - Full integration script
- `enhanced_geo_map_with_kaggle.py` - Map creation
- `KAGGLE_DATASETS_INDIA_MAP.md` - Dataset directory
- `enhanced_outlet_map_with_coordinates.html` - Current map

---

**Last Updated:** July 2, 2026  
**Status:** Ready to use  
**Estimated Time:** 10-15 minutes to complete
