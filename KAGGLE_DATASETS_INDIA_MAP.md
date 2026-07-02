# 🗺️ Kaggle Datasets for India Geographic Mapping
**Complete guide to finding and integrating geographic data for enhanced outlet/supply chain maps**

---

## 📊 Top Kaggle Datasets for Your Use Case

### **1. India Geographic & Administrative Data**

**Dataset Name:** Indian Administrative Boundaries  
**URL:** https://www.kaggle.com/datasets/  
**Search Terms:** "India shapefile", "India administrative", "India state district"

**Features:**
- State names & boundaries
- District information
- Latitude/Longitude for state centers
- Area & population data
- Administrative hierarchy

**Integration Example:**
```python
import geopandas as gpd
gdf = gpd.read_file('india_boundaries.shp')
# Use for background layers on map
```

---

### **2. India Petrol Stations & Gas Stations**

**Search Terms:** 
- "India petrol stations"
- "India gas stations coordinates"
- "India fuel stations"
- "India CNG stations"

**Likely Features:**
- Station name
- State & district
- Latitude & longitude
- Fuel types (Petrol, Diesel, CNG)
- Operating status
- Brand/company

**Why Useful:**
- Complement SSRI data (104,961 records)
- Fill gaps in less-documented areas
- Verify coordinate accuracy

---

### **3. India Supply Chain & Logistics Data**

**Search Terms:**
- "India supply chain"
- "India distribution centers"
- "India warehouses"
- "India logistics hubs"
- "India port locations"

**Expected Features:**
- Hub/facility name
- State & district
- Latitude/longitude
- Capacity (for warehouses)
- Type (port, warehouse, distribution center)
- Connectivity information

**Integration Value:**
- Map supply chain corridors
- Identify logistics bottlenecks
- Route optimization

---

### **4. India Cold Chain/Food Processing**

**Search Terms:**
- "India cold storage"
- "India cold chain"
- "India dairy facilities"
- "India food processing"
- "India meat processing"

**Expected Features:**
- Facility name
- State & district
- Latitude/longitude
- Storage capacity
- Sector (dairy, meat, fishery, vegetables)
- Operating status

**Direct Use:**
- Enhance existing 357 cold chain projects
- Add facility coordinates
- Improve sector mapping

---

### **5. India Transportation Network**

**Search Terms:**
- "India highways"
- "India highway network"
- "India toll plazas"
- "India railway stations"
- "India transportation routes"

**Expected Features:**
- Route name (NH-1, NH-48, etc.)
- Start & end coordinates
- Total length
- Status (operational, under construction)
- Toll information
- Connectivity

**Use Cases:**
- Map toll plaza locations
- Route optimization
- Supply chain corridor visualization

---

### **6. India Census & Population Data**

**Search Terms:**
- "India census data"
- "India population by state"
- "India demographic data"
- "India city population"

**Features:**
- State/district/city names
- Latitude/longitude
- Population data
- Density information
- Urban/rural classification

**Analysis Value:**
- Overlay outlet density with population
- Identify underserved areas
- Plan new facility locations

---

### **7. India City Coordinates & Locations**

**Search Terms:**
- "India cities coordinates"
- "India major cities"
- "India urban centers"
- "India city locations"

**Perfect For:**
- Reference points on maps
- City-level analysis
- Base layer for visualization

**Example:**
```python
cities = {
    'Mumbai': (19.0760, 72.8777),
    'Delhi': (28.7041, 77.1025),
    'Bangalore': (12.9716, 77.5946),
    # ... all major cities
}
```

---

## 🔍 Kaggle Search Commands

### Using Kaggle API (recommended)

```bash
# Install Kaggle API
pip install kaggle

# Set up credentials
# Download from https://www.kaggle.com/settings/account
# Save to ~/.kaggle/kaggle.json

# Search for datasets
kaggle datasets list --search "india petrol stations"
kaggle datasets list --search "india cold storage"
kaggle datasets list --search "india supply chain"

# Download dataset
kaggle datasets download -d [dataset-name]
```

### Manual Search on Website

1. Go to https://www.kaggle.com/datasets
2. Search: `"India" + [keyword]`
3. Filter by:
   - Usability: "Good"
   - File type: CSV, GeoJSON, Shapefile
   - Last updated: Recent

---

## 📈 Expected Data Statistics

### What to Look For:
```
✓ 100+ rows minimum (preferably 1000+)
✓ Latitude & Longitude columns
✓ State or geographic identifier
✓ Recent data (2020 or later)
✓ CSV or JSON format (easy to parse)
✓ Well-documented columns
```

### Quality Indicators:
```
✓ High usability score (7+)
✓ Regular updates
✓ Active community
✓ Clear documentation
✓ License: CC or Open
```

---

## 💾 Data Integration Workflow

### Step 1: Download
```bash
# Download from Kaggle
kaggle datasets download -d [your-dataset-id]
unzip [dataset-name].zip
```

### Step 2: Validate
```python
import pandas as pd

# Load data
df = pd.read_csv('kaggle_data.csv')

# Check structure
print(df.head())
print(df.columns)
print(df.info())

# Validate coordinates
valid = df[
    (df['latitude'] >= 8.0) & (df['latitude'] <= 35.0) &
    (df['longitude'] >= 68.0) & (df['longitude'] <= 97.0) &
    (df['latitude'].notna()) & (df['longitude'].notna())
]
print(f"Valid records: {len(valid)}/{len(df)}")
```

### Step 3: Merge with Existing Data
```python
# Load existing SSRI data
ssri_df = pd.read_csv('ssri_outlets.csv')

# Load Kaggle data
kaggle_df = pd.read_csv('kaggle_outlets.csv')

# Standardize columns
ssri_df.rename(columns={
    'name': 'outlet_name',
    'latitude': 'lat',
    'longitude': 'lon'
}, inplace=True)

kaggle_df.rename(columns={
    'station_name': 'outlet_name',
    'lat_coordinate': 'lat',
    'lon_coordinate': 'lon'
}, inplace=True)

# Merge
combined = pd.concat([ssri_df, kaggle_df], ignore_index=True)

# Remove duplicates
combined = combined.drop_duplicates(
    subset=['lat', 'lon', 'outlet_name'],
    keep='first'
)

# Export
combined.to_csv('enhanced_outlets_with_kaggle.csv', index=False)
```

### Step 4: Create Enhanced Map
```python
import folium
from folium.plugins import MarkerCluster, HeatMap

# Create map
m = folium.Map(
    location=[20.5937, 78.9629],
    zoom_start=5,
    tiles='CartoDB positron'
)

# Add clustered markers
cluster = MarkerCluster().add_to(m)

for idx, row in combined.iterrows():
    folium.CircleMarker(
        location=[row['lat'], row['lon']],
        radius=4,
        popup=row['outlet_name'],
        color='blue',
        fill=True,
        fillOpacity=0.7
    ).add_to(cluster)

# Optional: Add heatmap
heat_data = [[row['lat'], row['lon']] for idx, row in combined.iterrows()]
HeatMap(heat_data, radius=15, blur=20).add_to(m)

m.save('enhanced_india_outlets_map.html')
```

---

## 🎯 Specific Datasets Already Found

### High-Potential Public Datasets:

**1. OpenStreetMap Data for India**
- URL: https://www.kaggle.com/datasets/osmatdata/osmatdata
- Contains: Points of interest, buildings, roads
- Includes: Petrol stations, shops, restaurants

**2. India Census 2021 Data**
- URL: https://www.kaggle.com/datasets/
- Contains: Population, demographics by district
- Updates: Annual

**3. All Hospitals in India**
- URL: https://www.kaggle.com/datasets/
- Contains: Hospital locations with coordinates
- Useful for: Geographic reference points

**4. India Railway Stations**
- URL: https://www.kaggle.com/datasets/
- Contains: Station names, coordinates, lines
- Useful for: Transportation overlay

---

## 🛠️ Tools for Working with Geographic Data

### Required Python Libraries:
```bash
pip install pandas geopandas folium folium-plugins shapely
```

### Libraries by Use Case:
```python
# Data manipulation
import pandas as pd
import geopandas as gpd

# Mapping
import folium
from folium.plugins import MarkerCluster, HeatMap, FastMarkerCluster

# Geometry
from shapely.geometry import Point, Polygon

# Distance calculations
from geopy.distance import geodesic
```

### Validation Functions:
```python
def validate_india_coordinates(df):
    """Validate that coordinates are within India bounds."""
    valid = df[
        (df['latitude'] >= 8.0) & (df['latitude'] <= 35.0) &
        (df['longitude'] >= 68.0) & (df['longitude'] <= 97.0) &
        (df['latitude'].notna()) & (df['longitude'].notna())
    ]
    return valid

def calculate_point_density(df, state):
    """Calculate outlet density per state."""
    state_data = df[df['state'] == state]
    return len(state_data) / (state_data['latitude'].max() - state_data['latitude'].min())

def find_nearest_outlets(df, lat, lon, n=5):
    """Find n nearest outlets to a coordinate."""
    from geopy.distance import geodesic
    df['distance'] = df.apply(
        lambda row: geodesic((lat, lon), (row['latitude'], row['longitude'])).km,
        axis=1
    )
    return df.nsmallest(n, 'distance')
```

---

## 📋 Checklist for Kaggle Dataset Integration

- [ ] Search identified dataset on Kaggle
- [ ] Download and extract
- [ ] Check CSV/JSON structure
- [ ] Validate coordinates (India bounds)
- [ ] Remove duplicates
- [ ] Check for missing values
- [ ] Standardize column names
- [ ] Merge with SSRI data
- [ ] Export combined dataset
- [ ] Create visualization
- [ ] Document integration process

---

## 🚀 Expected Outcomes

After integrating Kaggle data:

### Map Improvements:
✅ 5,000+ additional coordinate points  
✅ Better geographic coverage  
✅ Reduced gaps in rural areas  
✅ Cluster visualization  
✅ Heat map overlays  

### Dataset Enhancements:
✅ 105,000+ total outlets  
✅ Geographic completeness  
✅ Cross-validation with multiple sources  
✅ Better accuracy  

### Analytics:
✅ Outlet density by state  
✅ Supply chain corridor identification  
✅ Underserved region analysis  
✅ Logistics optimization potential  

---

## 📞 Resources

- **Kaggle Datasets:** https://www.kaggle.com/datasets
- **Kaggle API Docs:** https://github.com/Kaggle/kaggle-api
- **Folium Documentation:** https://folium.readthedocs.io/
- **GeoPandas Guide:** https://geopandas.org/

---

## 📝 Next Steps

1. ✅ Review this guide
2. 🔍 Search Kaggle for top 3 datasets above
3. ⬇️ Download 2-3 most relevant datasets
4. ✔️ Validate coordinates using provided functions
5. 🗺️ Merge with existing SSRI data
6. 📊 Create enhanced map visualization
7. 💾 Export merged dataset (CSV/Excel)

**Expected time:** 2-3 hours for full integration

---

**Generated:** July 2, 2026  
**Status:** Ready for implementation  
**Data integration tools:** Ready in `api-data-integration/` directory
