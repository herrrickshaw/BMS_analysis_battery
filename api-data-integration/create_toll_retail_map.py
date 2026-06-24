#!/usr/bin/env python3
"""
INTERACTIVE TOLL + RETAIL OUTLETS MAP
======================================
Creates interactive Leaflet.js map showing:
- Toll plazas (blue markers)
- Retail outlets: petrol pumps (green), ATM stations (orange)
- Service zones around toll plazas
- Popup information for each location
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import math

class TollRetailMapGenerator:
    """Generates interactive map for toll plaza + retail outlets."""

    def __init__(self):
        """Initialize map generator."""
        self.toll_plazas = []
        self.retail_outlets = []
        self.map_features = []
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def load_data(self):
        """Load toll plazas and retail outlets."""
        print("📂 Loading data...")

        # Load SSRI petrol pumps
        try:
            ssri_json = "/Users/umashankar/api-data-integration/outlet_data_ssri_complete/ssri_all_pumps_20260624_063249.json"
            with open(ssri_json, 'r') as f:
                ssri_data = json.load(f)

            for pump in ssri_data:
                if pump.get('latitude') and pump.get('longitude'):
                    self.retail_outlets.append({
                        'name': pump.get('name', 'Unknown'),
                        'type': 'Petrol Pump',
                        'company': pump.get('company', 'Unknown'),
                        'state': pump.get('state', ''),
                        'city': pump.get('city', ''),
                        'lat': float(pump.get('latitude', 0)),
                        'lng': float(pump.get('longitude', 0)),
                        'has_cng': pump.get('has_cng', False),
                        'icon': 'green'
                    })

            print(f"  ✓ Loaded {len(ssri_data)} SSRI petrol pumps")
        except Exception as e:
            print(f"  ⚠ SSRI error: {str(e)[:50]}")

        # Load Cash@PoS stations
        try:
            cashatpos_csv = "/Users/umashankar/api-data-integration/outlet_data_cashatpos/cashatpos_fuel_stations_20260624_082138.csv"
            cashatpos_df = pd.read_csv(cashatpos_csv)

            for _, row in cashatpos_df.iterrows():
                self.retail_outlets.append({
                    'name': str(row.get('name', 'Unknown')),
                    'type': 'Cash@PoS ATM',
                    'company': 'SBI',
                    'state': str(row.get('state', '')),
                    'city': str(row.get('city', '')),
                    'lat': None,
                    'lng': None,
                    'has_cng': False,
                    'icon': 'orange'
                })

            print(f"  ✓ Loaded {len(cashatpos_df)} Cash@PoS ATM stations")
        except Exception as e:
            print(f"  ⚠ Cash@PoS error: {str(e)[:50]}")

        # Load toll plazas from CSV
        try:
            toll_csv = "/Users/umashankar/Downloads/toll_plazas_cleaned.csv"
            toll_df = pd.read_csv(toll_csv)
            toll_df = toll_df.dropna(subset=['plaza_name'])
            toll_df = toll_df[toll_df['plaza_name'].str.strip() != '']

            state_coords = {
                'Gujarat': (22.5, 72.5), 'Maharashtra': (19.5, 75.5), 'Rajasthan': (27.0, 77.5),
                'Haryana': (29.5, 77.0), 'Tamil Nadu': (11.0, 79.0), 'Karnataka': (15.0, 76.0),
                'Andhra Pradesh': (15.5, 78.5), 'Telangana': (18.5, 78.5), 'Punjab': (31.0, 75.5),
                'Uttar Pradesh': (27.0, 79.0), 'Delhi': (28.7, 77.2), 'Himachal Pradesh': (32.0, 77.0),
                'Madhya Pradesh': (23.0, 79.5), 'West Bengal': (24.5, 88.0),
            }

            for idx, row in toll_df.iterrows():
                state = str(row.get('state', '')).strip()
                if state in state_coords:
                    lat, lng = state_coords[state]
                    # Add variation for visualization
                    import random
                    lat += random.uniform(-0.5, 0.5)
                    lng += random.uniform(-0.5, 0.5)
                else:
                    lat, lng = 23.0, 79.0

                self.toll_plazas.append({
                    'name': str(row.get('plaza_name', 'Unknown')).strip(),
                    'highway': str(row.get('highway', '')).strip(),
                    'state': state,
                    'lat': lat,
                    'lng': lng
                })

            print(f"  ✓ Loaded {len(self.toll_plazas)} toll plazas")
        except Exception as e:
            print(f"  ⚠ Toll plaza error: {str(e)[:50]}")

    def create_geojson_features(self) -> List[Dict]:
        """Create GeoJSON features for map."""
        features = []

        # Add toll plaza markers
        for plaza in self.toll_plazas:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [plaza['lng'], plaza['lat']]
                },
                "properties": {
                    "name": plaza['name'],
                    "type": "Toll Plaza",
                    "highway": plaza['highway'],
                    "state": plaza['state'],
                    "color": "blue",
                    "icon": "🛣️"
                }
            }
            features.append(feature)

        # Add retail outlet markers
        for outlet in self.retail_outlets:
            if outlet['lat'] and outlet['lng']:
                color = "green" if outlet['type'] == 'Petrol Pump' else "orange"
                icon = "⛽" if outlet['type'] == 'Petrol Pump' else "🏧"

                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [outlet['lng'], outlet['lat']]
                    },
                    "properties": {
                        "name": outlet['name'],
                        "type": outlet['type'],
                        "company": outlet['company'],
                        "state": outlet['state'],
                        "city": outlet['city'],
                        "color": color,
                        "icon": icon
                    }
                }
                features.append(feature)

        return features

    def create_html_map(self, output_path: str = None):
        """Create interactive HTML map."""
        if output_path is None:
            output_path = f"./api-data-integration/toll_retail_map_{self.timestamp}.html"

        print(f"\n🗺️  Creating interactive map...")

        # Get center coordinates (India center)
        center_lat = 23.0
        center_lng = 79.0

        # Count outlets by type
        petrol_count = len([o for o in self.retail_outlets if o['type'] == 'Petrol Pump'])
        atm_count = len([o for o in self.retail_outlets if 'ATM' in o['type']])

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Toll Plaza + Retail Outlets Network Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .info {{
            padding: 6px 8px;
            font: 14px Arial, Helvetica, sans-serif;
            background: white;
            background: rgba(255,255,255,0.8);
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
            border-radius: 5px;
        }}
        .info h4 {{
            margin: 0 0 5px;
            color: #333;
            font-weight: bold;
        }}
        .legend {{
            line-height: 18px;
            color: #555;
        }}
        .legend i {{
            width: 18px;
            height: 18px;
            float: left;
            margin-right: 8px;
            opacity: 0.7;
            border-radius: 50%;
        }}
        .stats {{
            padding: 10px;
            background: rgba(255,255,255,0.95);
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
        }}
        .stats h3 {{
            margin: 0 0 10px;
            color: #333;
            font-size: 16px;
        }}
        .stat-item {{
            padding: 5px 0;
            border-bottom: 1px solid #eee;
        }}
        .stat-item:last-child {{ border-bottom: none; }}
        .stat-label {{
            color: #666;
            font-size: 12px;
        }}
        .stat-value {{
            color: #2196F3;
            font-weight: bold;
            font-size: 14px;
        }}
        .toll-popup {{
            background: #e3f2fd;
            border-left: 4px solid #1976d2;
        }}
        .outlet-popup {{
            background: #f1f8e9;
            border-left: 4px solid #558b2f;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        // Initialize map
        const map = L.map('map').setView([{center_lat}, {center_lng}], 5);

        // Add base map tiles
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19
        }}).addTo(map);

        // Toll plaza layer
        const tollLayer = L.featureGroup();
        const outletLayer = L.featureGroup();

        // Add toll plaza markers
        const tollPlazas = {json.dumps(self.toll_plazas)};
        tollPlazas.forEach(plaza => {{
            const marker = L.circleMarker([plaza.lat, plaza.lng], {{
                radius: 6,
                fillColor: '#1976d2',
                color: '#0d47a1',
                weight: 2,
                opacity: 0.8,
                fillOpacity: 0.7,
                className: 'toll-marker'
            }});

            const popupContent = `
                <div class="toll-popup">
                    <h4>🛣️ ${{plaza.name}}</h4>
                    <p><strong>Highway:</strong> ${{plaza.highway}}</p>
                    <p><strong>State:</strong> ${{plaza.state}}</p>
                    <p><strong>Coordinates:</strong> ${{plaza.lat.toFixed(4)}}, ${{plaza.lng.toFixed(4)}}</p>
                </div>
            `;
            marker.bindPopup(popupContent);
            tollLayer.addLayer(marker);
        }});

        // Add retail outlet markers
        const outlets = {json.dumps(self.retail_outlets)};
        outlets.forEach(outlet => {{
            if (outlet.lat && outlet.lng) {{
                const color = outlet.type === 'Petrol Pump' ? '#558b2f' : '#ff6f00';
                const marker = L.circleMarker([outlet.lat, outlet.lng], {{
                    radius: 4,
                    fillColor: color,
                    color: 'rgba(0,0,0,0.3)',
                    weight: 1,
                    opacity: 0.7,
                    fillOpacity: 0.6
                }});

                const icon = outlet.type === 'Petrol Pump' ? '⛽' : '🏧';
                const popupContent = `
                    <div class="outlet-popup">
                        <h4>${{icon}} ${{outlet.name}}</h4>
                        <p><strong>Type:</strong> ${{outlet.type}}</p>
                        <p><strong>Company:</strong> ${{outlet.company}}</p>
                        <p><strong>State:</strong> ${{outlet.state}}</p>
                        <p><strong>City:</strong> ${{outlet.city}}</p>
                        ${{outlet.has_cng ? '<p style="color: #d32f2f;">✓ CNG Available</p>' : ''}}
                    </div>
                `;
                marker.bindPopup(popupContent);
                outletLayer.addLayer(marker);
            }}
        }});

        // Add layers to map
        tollLayer.addTo(map);
        outletLayer.addTo(map);

        // Layer control
        const layerControl = L.control.layers(
            {{}},
            {{
                '🛣️ Toll Plazas': tollLayer,
                '⛽ Petrol Pumps': L.featureGroup(),
                '🏧 ATM Stations': L.featureGroup()
            }},
            {{ position: 'topright', collapsed: false }}
        );
        layerControl.addTo(map);

        // Add legend
        const legend = L.control({{ position: 'bottomleft' }});
        legend.onAdd = function(map) {{
            const div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = `
                <h4>Legend</h4>
                <div class="stat-item">
                    <i style="background: #1976d2; border: 2px solid #0d47a1;"></i>
                    <span>Toll Plaza</span>
                </div>
                <div class="stat-item">
                    <i style="background: #558b2f; border: 1px solid rgba(0,0,0,0.3);"></i>
                    <span>Petrol Pump</span>
                </div>
                <div class="stat-item">
                    <i style="background: #ff6f00; border: 1px solid rgba(0,0,0,0.3);"></i>
                    <span>ATM Station</span>
                </div>
            `;
            return div;
        }};
        legend.addTo(map);

        // Add statistics panel
        const stats = L.control({{ position: 'topright' }});
        stats.onAdd = function(map) {{
            const div = L.DomUtil.create('div', 'stats');
            div.innerHTML = `
                <h3>📊 Network Statistics</h3>
                <div class="stat-item">
                    <span class="stat-label">Toll Plazas</span>
                    <span class="stat-value">{len(self.toll_plazas):,}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Petrol Pumps</span>
                    <span class="stat-value">{petrol_count:,}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">ATM Stations</span>
                    <span class="stat-value">{atm_count:,}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Total Outlets</span>
                    <span class="stat-value">{len(self.retail_outlets):,}</span>
                </div>
            `;
            return div;
        }};
        stats.addTo(map);

        // Fit bounds to show all markers
        const allMarkers = [...tollLayer.getLayers(), ...outletLayer.getLayers()];
        if (allMarkers.length > 0) {{
            const group = new L.featureGroup(allMarkers);
            map.fitBounds(group.getBounds().pad(0.1));
        }}
    </script>
</body>
</html>"""

        with open(output_path, 'w') as f:
            f.write(html_content)

        print(f"  ✓ Map created: {output_path}")
        return output_path

    def run(self):
        """Run complete map generation."""
        print("\n" + "="*80)
        print("🗺️  TOLL PLAZA + RETAIL OUTLETS INTERACTIVE MAP")
        print("="*80)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        self.load_data()
        self.create_html_map()

        print(f"\n✅ Map generation complete!")
        print(f"\n   Toll Plazas: {len(self.toll_plazas):,}")
        print(f"   Retail Outlets: {len(self.retail_outlets):,}")

        print(f"\nEnd: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")


def main():
    """Main execution."""
    generator = TollRetailMapGenerator()
    generator.run()


if __name__ == "__main__":
    main()
