
# KAGGLE DATASET INTEGRATION GUIDE
==================================

## Recommended Kaggle Datasets to Download

### 1. India Gas Stations/Petrol Pumps
**Search:** "India petrol stations" or "India gas stations"
**Expected Features:**
  - name: Station name
  - state: Indian state
  - district: District name
  - latitude: Decimal degrees (8-35)
  - longitude: Decimal degrees (68-97)
  - fuel_types: Available fuels
  - company: Oil company (IOCL, BPCL, HPCL)

**How to use:**
```python
import pandas as pd
df = pd.read_csv('kaggle_petrol_stations.csv')
# Validate coordinates
df = df[(df['latitude'] >= 8) & (df['latitude'] <= 35)]
df = df[(df['longitude'] >= 68) & (df['longitude'] <= 97)]
```

### 2. India Cold Storage/Supply Chain Data
**Search:** "India cold chain" or "India cold storage"
**Expected Features:**
  - facility_name: Cold chain facility name
  - state: Location state
  - latitude: Facility latitude
  - longitude: Facility longitude
  - capacity_mt: Storage capacity in MT
  - sector: Dairy, Fishery, FAV, etc.

### 3. India Geographic/Administrative Data
**Search:** "India shapefile" or "India administrative boundaries"
**Expected Features:**
  - state: State name
  - district: District name
  - latitude: State/district center
  - longitude: State/district center
  - area_km2: Geographic area
  - population: Population data

### 4. India Transportation Network
**Search:** "India highways" or "India transportation"
**Expected Features:**
  - highway_name: Road name (NH-1, NH-48, etc.)
  - route: Start to end points
  - latitude_start, longitude_start: Route start
  - latitude_end, longitude_end: Route end

## Integration Steps

### Step 1: Download from Kaggle
```bash
# Install Kaggle CLI
pip install kaggle

# Create ~/.kaggle/kaggle.json with API credentials
# Download dataset
kaggle datasets download -d [dataset-name]
```

### Step 2: Validate Coordinates
```python
def validate_coordinates(df):
    # Check bounds
    valid = df[
        (df['latitude'] >= 8.0) & (df['latitude'] <= 35.0) &
        (df['longitude'] >= 68.0) & (df['longitude'] <= 97.0)
    ]

    # Remove nulls
    valid = valid.dropna(subset=['latitude', 'longitude'])

    return valid
```

### Step 3: Merge with Existing Data
```python
ssri_df = pd.read_csv('ssri_outlets.csv')
kaggle_df = pd.read_csv('kaggle_outlets.csv')

# Merge and deduplicate
merged = pd.concat([ssri_df, kaggle_df], ignore_index=True)
merged = merged.drop_duplicates(subset=['latitude', 'longitude'])
```

### Step 4: Create Enhanced Map
```python
import folium
from folium.plugins import MarkerCluster

m = folium.Map(
    location=[20.5937, 78.9629],  # India center
    zoom_start=5,
    tiles='CartoDB positron'
)

# Add clustered markers
cluster = MarkerCluster().add_to(m)

for idx, row in merged.iterrows():
    folium.CircleMarker(
        location=[row['latitude'], row['longitude']],
        radius=4,
        popup=f"{row['name']} - {row['state']}",
        color='blue',
        fill=True
    ).add_to(cluster)

m.save('enhanced_map.html')
```

## Data Quality Checks

### Latitude/Longitude Validation
- India bounds: 8.0°N to 35.0°N (latitude)
- India bounds: 68.0°E to 97.0°E (longitude)
- No null values
- No zero coordinates (0,0 indicates missing data)

### Duplicate Detection
```python
# Find potential duplicates
duplicates = merged[
    merged.duplicated(subset=['latitude', 'longitude'], keep=False)
]
```

### Accuracy Assessment
- Check for outliers (very high/low lat/lon)
- Verify state matches latitude/longitude region
- Compare with known reference points

## Popular Open Datasets on Kaggle

1. **India Administrative Divisions**
   - States, districts, boundaries
   - Links: Often included in geographic datasets

2. **India Census Data**
   - Population by state/district
   - Area information

3. **India Transportation Network**
   - Highway routes with coordinates
   - Railway stations

4. **India Urban Centers**
   - Major cities with coordinates
   - Population density

## Integration with Cold Chain + Outlet Map

Combine:
1. SSRI petrol pumps (existing 104,961 records)
2. Kaggle petrol stations (additional coverage)
3. Cold chain facilities (357 projects)
4. Geographic boundaries (state/district)

Result: Comprehensive supply chain infrastructure map

## Verification

After integration:
```python
# Check coverage
print(f"Total outlets: {len(merged)}")
print(f"States covered: {merged['state'].nunique()}")
print(f"Valid coordinates: {merged[['latitude', 'longitude']].notna().all(axis=1).sum()}")

# State-wise statistics
print(merged.groupby('state').size().sort_values(ascending=False).head(10))
```

## Next Steps

1. Search Kaggle with keywords above
2. Download 2-3 most relevant datasets
3. Validate coordinates using provided functions
4. Merge with existing SSRI data
5. Create enhanced map
6. Export merged dataset to CSV/Excel for future use
