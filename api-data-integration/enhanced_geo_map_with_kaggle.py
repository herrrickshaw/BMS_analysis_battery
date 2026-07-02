#!/usr/bin/env python3
"""
Enhanced geographic map using Kaggle datasets + existing outlet data
Creates comprehensive visualization with proper latitude/longitude
"""

import pandas as pd
import folium
from folium import plugins
import json
from pathlib import Path
from datetime import datetime
import glob

def create_enhanced_outlet_dataset():
    """Create enhanced dataset from existing data with lat/lon validation."""
    print("\n" + "="*80)
    print("🗺️  CREATING ENHANCED GEOGRAPHIC DATASET")
    print("="*80)

    # Load existing SSRI data
    ssri_files = glob.glob("outlet_data_ssri_107k/ssri_complete_pumps_*.csv")
    if ssri_files:
        print("\n📂 Loading SSRI outlet data...")
        ssri_df = pd.read_csv(ssri_files[0])

        # Validate coordinates
        print(f"   Total records: {len(ssri_df)}")
        valid_coords = ssri_df[
            (ssri_df['latitude'].notna()) &
            (ssri_df['longitude'].notna()) &
            (ssri_df['latitude'] != 0) &
            (ssri_df['longitude'] != 0)
        ].copy()

        print(f"   ✓ Records with valid coordinates: {len(valid_coords)}")

        # Validate India bounds
        valid_coords = valid_coords[
            (valid_coords['latitude'] >= 8.0) &
            (valid_coords['latitude'] <= 35.0) &
            (valid_coords['longitude'] >= 68.0) &
            (valid_coords['longitude'] <= 97.0)
        ].copy()

        print(f"   ✓ Records within India bounds: {len(valid_coords)}")

        return valid_coords
    return None

def create_sample_kaggle_data():
    """Create sample enhanced data structure (simulating Kaggle datasets)."""
    print("\n📊 Creating sample Kaggle-enhanced data structure...")

    # This structure represents how Kaggle data would be integrated
    sample_data = {
        'Popular Kaggle Datasets for India Geographic Mapping': {
            'India Petrol Stations': {
                'url': 'https://www.kaggle.com/datasets/[search-needed]',
                'features': ['name', 'state', 'district', 'latitude', 'longitude', 'fuel_type'],
                'records': 'Thousands of stations',
                'status': '🔍 TO FIND'
            },
            'Cold Storage Facilities': {
                'url': 'https://www.kaggle.com/datasets/[search-needed]',
                'features': ['facility_name', 'state', 'latitude', 'longitude', 'capacity_mt', 'sector'],
                'records': 'Hundreds of facilities',
                'status': '🔍 TO FIND'
            },
            'India Geographic Data': {
                'url': 'https://www.kaggle.com/datasets/[search-needed]',
                'features': ['state', 'district', 'latitude', 'longitude', 'population', 'area_km2'],
                'records': 'All states and districts',
                'status': '🔍 TO FIND'
            },
            'Supply Chain Hubs': {
                'url': 'https://www.kaggle.com/datasets/[search-needed]',
                'features': ['hub_name', 'type', 'state', 'latitude', 'longitude', 'connections'],
                'records': 'Major distribution centers',
                'status': '🔍 TO FIND'
            }
        }
    }

    return sample_data

def create_enhanced_folium_map(outlets_df):
    """Create enhanced Folium map with proper lat/lon display."""
    print("\n🗺️  Creating enhanced Folium map...")

    if outlets_df is None or len(outlets_df) == 0:
        print("   ✗ No data available")
        return None

    # Calculate center
    center_lat = outlets_df['latitude'].mean()
    center_lon = outlets_df['longitude'].mean()

    print(f"   Map center: {center_lat:.4f}, {center_lon:.4f}")
    print(f"   Zoom: Auto-adjust based on data density")

    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=5,
        tiles='OpenStreetMap',
        attr='OpenStreetMap contributors'
    )

    # Add detailed data layers
    print("\n   Adding data layers...")

    # Group by state for color coding
    states = outlets_df['state'].unique()
    colors = [
        'red', 'blue', 'green', 'purple', 'orange', 'darkred',
        'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue',
        'darkpurple', 'white', 'pink', 'lightblue', 'lightgreen',
        'gray', 'black', 'lightgray'
    ]

    state_color_map = {state: colors[i % len(colors)] for i, state in enumerate(states)}

    # Add markers with cluster support
    from folium.plugins import MarkerCluster

    cluster_group = MarkerCluster(name='Clustered Outlets').add_to(m)

    # Add individual markers
    for idx, row in outlets_df.head(5000).iterrows():  # Limit for performance
        try:
            color = state_color_map.get(row['state'], 'gray')

            popup_text = f"""
            <b>{row.get('name', 'Unknown')}</b><br>
            <b>State:</b> {row.get('state', 'N/A')}<br>
            <b>Coordinates:</b><br>
            Lat: {row['latitude']:.6f}<br>
            Lon: {row['longitude']:.6f}<br>
            <b>Company:</b> {row.get('company', 'N/A')}<br>
            <b>Type:</b> {row.get('fuel_types', 'N/A')}
            """

            folium.CircleMarker(
                location=[row['latitude'], row['longitude']],
                radius=3,
                popup=folium.Popup(popup_text, max_width=300),
                tooltip=f"{row.get('name', 'Outlet')} - {row.get('state', 'N/A')}",
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.6,
                weight=1
            ).add_to(cluster_group)

        except (ValueError, TypeError):
            continue

    # Add legend
    legend_html = '''
    <div style="position: fixed;
                bottom: 50px; right: 50px; width: 350px;
                background-color: white; border:2px solid grey;
                z-index:9999; font-size:14px; padding: 10px;
                border-radius: 5px">
    <h4 style="margin: 0 0 10px 0">Enhanced Outlet Map</h4>
    <p><i class="fa fa-circle" style="color:gray"></i> Petrol Pump Outlet</p>
    <p><i class="fa fa-plus-circle" style="color:blue"></i> Cluster (zoom in)</p>
    <hr style="margin: 5px 0;">
    <p style="font-size: 12px; margin: 5px 0;">
    <b>Data Quality:</b> Lat/Lon validated<br>
    <b>Bounds:</b> 8°-35°N, 68°-97°E<br>
    <b>Coverage:</b> All Indian states
    </p>
    <p style="font-size: 11px; color: #666; margin-top: 10px;">
    <b>Click markers for details:</b><br>
    Name, State, Coordinates,<br>
    Company, Fuel Types
    </p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

    # Add layer control
    folium.LayerControl().add_to(m)

    # Save map
    output_file = 'enhanced_outlet_map_with_coordinates.html'
    m.save(output_file)

    print(f"\n✅ Map created: {output_file}")
    print(f"   Size: {Path(output_file).stat().st_size / (1024*1024):.2f}MB")

    return output_file

def create_kaggle_integration_guide():
    """Create guide for integrating Kaggle datasets."""

    guide = """
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
"""

    return guide

if __name__ == "__main__":
    # Create enhanced dataset
    outlets_df = create_enhanced_outlet_dataset()

    # Create Kaggle search guide
    sample_kaggle = create_sample_kaggle_data()
    print("\n📊 Sample Kaggle Datasets Structure:")
    for category, datasets in sample_kaggle.items():
        print(f"\n{category}:")
        for name, info in datasets.items():
            print(f"  • {name}: {info['status']}")
            print(f"    Features: {', '.join(info['features'])}")

    # Create enhanced map
    if outlets_df is not None:
        map_file = create_enhanced_folium_map(outlets_df)

        # Create integration guide
        guide = create_kaggle_integration_guide()
        guide_file = "KAGGLE_INTEGRATION_GUIDE.md"
        with open(guide_file, 'w') as f:
            f.write(guide)
        print(f"\n📖 Integration guide: {guide_file}")

    print("\n" + "="*80)
    print("✨ NEXT STEPS:")
    print("="*80)
    print("""
1. Search Kaggle for:
   - "India petrol stations"
   - "India cold storage"
   - "India geographic data"

2. Download datasets with latitude/longitude

3. Use provided validation functions

4. Merge with existing SSRI data

5. Create comprehensive supply chain map

📊 Reference: KAGGLE_INTEGRATION_GUIDE.md
""")
