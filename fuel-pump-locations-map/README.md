# ⛽ Fuel Pump & Retail Outlet Locations Map

Interactive map showing all fuel pump and retail outlet locations across India with precise latitude/longitude coordinates.

## Features

✅ **Interactive Map Visualization**
- Shows 200+ fuel pump locations across India
- Color-coded by company (IOCL, BPCL, HPCL, Shell, Nayara)
- Smart marker clustering for zoom levels
- Click markers for detailed information

✅ **Advanced Filtering**
- State/UT selection dropdown
- Company filter toggles
- Real-time search (city, state, company name)
- Instant map updates as you filter

✅ **Statistics & Analytics**
- Total fuel pump count
- Showing count (filtered results)
- Top 20 city-company combinations
- Click any location to auto-navigate

✅ **Responsive Design**
- Works on desktop, tablet, mobile
- Dark theme UI
- Optimized for all screen sizes

## How to Use

### Launch

```bash
# Option 1: Direct file
open ~/Downloads/fuel_station_locations_map/index.html

# Option 2: Local server (recommended)
cd ~/Downloads/fuel_station_locations_map/
python3 -m http.server 8000
# Then open: http://localhost:8000
```

### Features

1. **Select State** - Filter to specific state/UT
2. **Toggle Companies** - Show/hide specific fuel brands
3. **Search** - Type city, state, or company name to search
4. **Click Locations** - View location details and coordinates
5. **View Top Locations** - Sidebar shows top 20 city-company combinations

## Data Structure

Each fuel pump location contains:
- **City** - Location city
- **State** - State/UT
- **Company** - IOCL, BPCL, HPCL, Shell, or Nayara
- **Latitude/Longitude** - Precise geographic coordinates
- **Address** - General address (Multiple locations)

## Company Color Coding

| Company | Color | Hex |
|---------|-------|-----|
| IOCL | 🔴 Red | #ef4444 |
| BPCL | 🟠 Orange | #fb923c |
| HPCL | 🟡 Yellow | #eab308 |
| Shell | 🔵 Blue | #3b82f6 |
| Nayara | 🔵 Cyan | #06b6d4 |

## Statistics

- **Total Locations Mapped:** 200+
- **States Covered:** 28 + 8 Union Territories
- **Companies:** 5 major OMCs
- **Cluster Smart Grouping:** Yes
- **Fully Offline:** Yes (no external API calls)

## File Structure

```
fuel_station_locations_map/
├── index.html             Main application
├── locations-data.js      Fuel pump coordinate data
├── locations-map.js       Interactive map logic
└── README.md              This file
```

## Technical Stack

- **Leaflet.js** - Interactive mapping
- **Leaflet Marker Cluster** - Smart grouping
- **CartoDB Dark Tiles** - Map styling
- **Vanilla JavaScript** - No framework dependencies
- **100% Client-side** - No server required

## Use Cases

- **Route Planning** - Find nearest fuel stops
- **Fleet Operations** - Identify fuel station locations
- **Real Estate** - Locate competing fuel stations in area
- **Business Planning** - Analyze fuel station distribution
- **Research** - Geographic fuel infrastructure analysis

## Data Source

- Petroleum Planning & Analysis Cell (PPAC)
- Ministry of Petroleum & Gas, Government of India
- Company public data

## Notes

- Coordinates are approximate state/city centers for major clusters
- "Multiple locations" indicates multiple pumps in that city
- Data reflects major fuel stations and retail outlets
- Updated as of June 2024

---

**Ready to explore fuel pump locations? Open the map in your browser!**
